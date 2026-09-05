#include <gecode/int.hh>
#include <gecode/minimodel.hh>
#include <gecode/search.hh>
#include <gecode/minimodel/lp-model.hpp>
#ifdef WITH_LP
#include <gecode/minimodel/lp-relaxation.hpp>
#include <gecode/minimodel/lp-strengthening.hpp>
#include <gecode/minimodel/lp-primal.hpp>
#endif
#include "policy.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <memory>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/resource.h>

using namespace Gecode;
namespace LP = Gecode::Experimental::LpRelaxation;
using Clock=std::chrono::steady_clock;

struct Instance {
  LP::LinearModel model;
  std::vector<int> incumbent;
  int incumbent_cost=0;
  int lo=0,hi=0;
  explicit Instance(const char* path) {
    std::ifstream f(path);
    int n,m;
    if (!(f>>n>>m) || n<=0 || n>10000 || m<0 || m>10000 || 1LL*n*m>10000000)
      throw std::runtime_error("Invalid dimensions");
    model.c.resize(n); model.b.resize(m); model.a.assign(n*m,0);
    for (auto& c:model.c) if (!(f>>c)) throw std::runtime_error("Invalid objective");
    for (int i=0;i<m;++i) {
      int count;
      if (!(f>>model.b[i]>>count) || count<0 || count>n)
        throw std::runtime_error("Invalid row");
      int previous=-1;
      for (int k=0;k<count;++k) {
        int j; std::int64_t a;
        if (!(f>>j>>a) || j<=previous || j>=n || !a)
          throw std::runtime_error("Invalid coefficient");
        previous=j; model.a[i*n+j]=a;
      }
    }
    LP::validate_model(model);
    for (auto c:model.c) { if (c<0) lo+=static_cast<int>(c); else hi+=static_cast<int>(c); }
    std::string label;
    int present;
    if (!(f>>label>>present) || label!="incumbent" || (present!=0 && present!=1))
      throw std::runtime_error("Invalid incumbent trailer");
    if (present) {
      incumbent.resize(n);
      for (int& value:incumbent)
        if (!(f>>value) || (value!=0 && value!=1)) throw std::runtime_error("Invalid incumbent bit");
      for (int i=0;i<m;++i) {
        std::int64_t lhs=0;
        for (int j=0;j<n;++j) lhs+=model.a[i*n+j]*incumbent[j];
        if (lhs<model.b[i]) throw std::runtime_error("Incumbent violates a constraint");
      }
      for (int j=0;j<n;++j) incumbent_cost+=static_cast<int>(model.c[j])*incumbent[j];
    }
  }
};

struct Configuration {
  std::string mode,branching;
  bool warm;
  const LP::LinearModel* matrix=nullptr;
  int incumbent_cost=0;
  std::vector<int> fixings;
#ifdef WITH_LP
  std::shared_ptr<LP::Backend> backend;
  LP::Options options;
#endif
};

// Algebraic features only; no family label, seed, reference or test outcome.
std::vector<double> features(const LP::LinearModel& m) {
  double n=m.c.size(),rows=m.b.size(),nnz=0,unit=0,negative=0,nonzero=0;
  double positive_rows=0,negative_rows=0,pairs=0,max_coefficient=0;
  for(auto c:m.c){negative+=c<0;nonzero+=c!=0;}
  for(std::size_t i=0;i<m.b.size();++i){int count=0;bool pos=true,neg=true;
    for(std::size_t j=0;j<m.c.size();++j){auto a=m.a[i*m.c.size()+j];if(a){++count;unit+=std::abs(a)==1;max_coefficient=std::max(max_coefficient,static_cast<double>(std::abs(a)));pos&=a>0;neg&=a<0;}}
    nnz+=count;positive_rows+=pos;negative_rows+=neg;pairs+=count==2;
  }
  return {n,rows,rows/std::max(1.0,n),nnz/std::max(1.0,n*rows),negative/std::max(1.0,n),
    nonzero/std::max(1.0,n),unit/std::max(1.0,nnz),positive_rows/std::max(1.0,rows),
    negative_rows/std::max(1.0,rows),pairs/std::max(1.0,rows),max_coefficient,nnz/std::max(1.0,rows)};
}

class Model : public IntMinimizeSpace {
public:
  IntVarArray x;
  IntVar objective;
  const LP::LinearModel* matrix;
  Model(const Instance& p,const Configuration& cfg)
      : x(*this,static_cast<int>(p.model.c.size()),0,1),objective(*this,p.lo,p.hi),matrix(cfg.matrix) {
#ifdef WITH_LP
    if (cfg.backend)
      LP::binary_linear_minimize(*this,x,objective,cfg.backend,cfg.options);
    else
#endif
      LP::post_native(*this,x,objective,*matrix);
    if (cfg.warm) rel(*this,objective,IRT_LE,cfg.incumbent_cost);
    for(std::size_t j=0;j<cfg.fixings.size();++j)
      if(cfg.fixings[j]>=0)rel(*this,x[static_cast<int>(j)],IRT_EQ,cfg.fixings[j]);
    // The same objective-aware value order and variable rule in both solvers.
    IntValBranch values=INT_VAL([](const Space& home,IntVar x,int j){return static_cast<const Model&>(home).matrix->c[j]<0?x.max():x.min();});
    if (cfg.branching=="afc") branch(*this,x,INT_VAR_AFC_SIZE_MAX(0.99),values);
    else if (cfg.branching=="size") branch(*this,x,INT_VAR_SIZE_MIN(),values);
    else if (cfg.branching=="degree") branch(*this,x,INT_VAR_DEGREE_SIZE_MAX(),values);
    else throw std::runtime_error("Unknown branching policy");
  }
  Model(Model& other):IntMinimizeSpace(other),matrix(other.matrix) {x.update(*this,other.x);objective.update(*this,other.objective);}
  Space* copy() override {return new Model(*this);}
  IntVar cost() const override {return objective;}
};

int main(int argc,char** argv) {
  try {
    if (argc!=7) throw std::runtime_error("Usage: driver INPUT none|root|node afc|size LIMIT_MS WARM_START REPEATS");
    Instance input(argv[1]);
    std::string requested=argv[2],branching=argv[3];
    double limit=std::stod(argv[4]);
    bool warm=std::stoi(argv[5])!=0;
    int repeats=std::stoi(argv[6]);
    const std::vector<std::string> modes={"native","lp","fix","fix4","fix8","rootfix","cuts-native","cuts-lp","cuts-fix","cuts-fix4","presolve","lns-native","lns-fix4","pump","pump-fix4","cuts-pump-fix4","auto"};
    if (std::find(modes.begin(),modes.end(),requested)==modes.end() || !std::isfinite(limit) || limit<=0 || limit>86400000 || repeats<=0)
      throw std::runtime_error("Invalid mode or budget");
#ifndef WITH_LP
    if (requested!="native") throw std::runtime_error("Stock executable has no experimental features");
#endif
    for (int repetition=0;repetition<repeats;++repetition) {
      const auto begin=Clock::now();
      Search::TimeStop stop(limit);
      const auto f=features(input.model);
      std::string mode=requested=="auto"?select_policy(f):requested;
      Configuration cfg; cfg.mode=mode;cfg.branching=branching;cfg.warm=warm&&!input.incumbent.empty();cfg.incumbent_cost=input.incumbent_cost;
      LP::LinearModel strengthened;cfg.matrix=&input.model;
      std::size_t cuts=0,cliques=0,covers=0,gcd_rows=0;
#ifdef WITH_LP
      if(mode.find("cuts-")==0 || mode=="presolve") {
        LP::Strengthening::Options cut_options;if(mode=="presolve")cut_options.max_cuts=0;
        auto result=LP::Strengthening::strengthen(input.model,cut_options);
        cuts=result.stats.cuts_added();cliques=result.stats.clique_cuts;covers=result.stats.cover_cuts;gcd_rows=result.stats.gcd_rows;
        strengthened=std::move(result.model);cfg.matrix=&strengthened;
      }
      bool use_lp=mode!="native" && mode!="cuts-native" && mode!="presolve" && mode!="lns-native" && mode!="pump";
      cfg.options.reduced_cost_fixing=mode.find("fix")!=std::string::npos;
      cfg.options.assignment_interval=mode.find("fix4")!=std::string::npos?4:mode.find("fix8")!=std::string::npos?8:1;
      if(mode=="rootfix")cfg.options.frequency=LP::Frequency::Root;
      if (use_lp) cfg.backend=std::make_shared<LP::Backend>(*cfg.matrix);
#endif
      std::vector<int> best;
      int best_cost=0;
      if (warm && !input.incumbent.empty()) {best=input.incumbent;best_cost=input.incumbent_cost;}
      std::vector<std::pair<double,int>> improvements;
      std::uint64_t heuristic_nodes=0;unsigned neighborhoods=0;
      std::uint64_t primal_lp_calls=0,primal_exact_checks=0;double primal_ms=0;bool primal_found=false;
#ifdef WITH_LP
      if(mode.find("pump")!=std::string::npos) {
        LP::Primal::Options options;
        double remaining=limit-std::chrono::duration<double,std::milli>(Clock::now()-begin).count();
        options.wall_budget_ms=std::max(0.0,std::min({50.0,limit*.10,remaining}));
        if(!best.empty())options.strict_cutoff=best_cost;
        auto candidate=LP::Primal::generate(input.model,options);
        primal_lp_calls=candidate.lp_calls;primal_exact_checks=candidate.exact_checks;primal_ms=candidate.elapsed_ms;primal_found=candidate.found;
        if(candidate.found){best=std::move(candidate.assignment);best_cost=static_cast<int>(candidate.cost);cfg.warm=true;cfg.incumbent_cost=best_cost;improvements.emplace_back(std::chrono::duration<double,std::milli>(Clock::now()-begin).count(),best_cost);}
      }
#endif
      // Bounded incumbent repair, followed by a fresh unrestricted proof search.
      if(mode.find("lns-")==0 && !best.empty()) {
        auto heuristic_deadline=begin+std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double,std::milli>(std::min(100.0,limit*.15)));
        std::mt19937 random(9173);
        for(unsigned attempt=0;attempt<8 && Clock::now()<heuristic_deadline;++attempt){
          cfg.fixings=best;std::vector<int> indices(best.size());std::iota(indices.begin(),indices.end(),0);std::shuffle(indices.begin(),indices.end(),random);
          const std::size_t free=std::min(best.size(),std::max<std::size_t>(6,best.size()*(attempt%3+1)/5));
          for(std::size_t j=0;j<free;++j)cfg.fixings[indices[j]]=-1;
          cfg.warm=true;cfg.incumbent_cost=best_cost;
          double remaining=std::chrono::duration<double,std::milli>(heuristic_deadline-Clock::now()).count();
          if(remaining<=0)break;
          Search::TimeStop local_stop(std::max(1.0,std::min(15.0,remaining)));
          Search::Options local_options;local_options.threads=1;local_options.stop=&local_stop;
          auto neighborhood=std::make_unique<Model>(input,cfg);
          {BAB<Model> engine(neighborhood.get(),local_options);neighborhood.reset();while(Model*solution=engine.next()){
            for(int j=0;j<solution->x.size();++j)best[j]=solution->x[j].val();best_cost=solution->objective.val();delete solution;
            improvements.emplace_back(std::chrono::duration<double,std::milli>(Clock::now()-begin).count(),best_cost);
          }heuristic_nodes+=engine.statistics().node;}
          ++neighborhoods;
        }
        cfg.fixings.clear();cfg.incumbent_cost=best_cost;
      }
      auto root=std::make_unique<Model>(input,cfg);
      const auto constructed=Clock::now();
      Search::Options options;options.threads=1;options.stop=&stop;
      Search::Statistics statistics;
      bool stopped;
      {
        BAB<Model> engine(root.get(),options);root.reset();
        while (Model* solution=engine.next()) {
          best.resize(solution->x.size());
          for (int j=0;j<solution->x.size();++j) best[j]=solution->x[j].val();
          best_cost=solution->objective.val();
          delete solution;
          improvements.emplace_back(std::chrono::duration<double,std::milli>(Clock::now()-begin).count(),best_cost);
        }
        statistics=engine.statistics();stopped=engine.stopped();
      }
      std::uint64_t lp_calls=0,valid_bounds=0,rejected=0,lp_infeasible=0;
      std::uint64_t conditional_checks=0,variable_fixings=0;
      double lp_ms=0;
#ifdef WITH_LP
      if (cfg.backend) {
        auto s=cfg.backend->statistics();lp_calls=s.lp_calls;lp_ms=s.lp_ms;
        valid_bounds=s.valid_bounds;rejected=s.rejected;lp_infeasible=s.infeasible_status;
        conditional_checks=s.conditional_checks;variable_fixings=s.variable_fixings;
        cfg.backend.reset();
      }
#endif
      strengthened=LP::LinearModel{};
      const auto finished=Clock::now();
      struct rusage usage;getrusage(RUSAGE_SELF,&usage);
      long rss=usage.ru_maxrss;
#ifdef __APPLE__
      rss/=1024;
#endif
      const char* status=best.empty() ? (stopped?"unknown":"infeasible") : (stopped?"feasible":"optimal");
      std::cout << "{\"status\":\"" << status << "\",\"mode\":\"" << mode << "\",\"requested_mode\":\"" << requested << "\",\"branching\":\"" << branching
                << "\",\"stopped\":" << (stopped?"true":"false")
                << ",\"elapsed_ms\":" << std::chrono::duration<double,std::milli>(finished-begin).count()
                << ",\"build_ms\":" << std::chrono::duration<double,std::milli>(constructed-begin).count()
                << ",\"pre_proof_ms\":" << std::chrono::duration<double,std::milli>(constructed-begin).count()
                << ",\"lp_ms\":" << lp_ms << ",\"lp_calls\":" << lp_calls
                << ",\"certified_bounds\":" << valid_bounds << ",\"rejected_bounds\":" << rejected
                << ",\"lp_infeasible_statuses\":" << lp_infeasible << ",\"nodes\":" << statistics.node
                << ",\"conditional_checks\":" << conditional_checks << ",\"variable_fixings\":" << variable_fixings
                << ",\"cuts\":" << cuts << ",\"clique_cuts\":" << cliques << ",\"cover_cuts\":" << covers << ",\"gcd_rows\":" << gcd_rows
                << ",\"heuristic_nodes\":" << heuristic_nodes << ",\"neighborhoods\":" << neighborhoods
                << ",\"total_nodes\":" << (statistics.node+heuristic_nodes)
                << ",\"primal_lp_calls\":" << primal_lp_calls << ",\"primal_exact_checks\":" << primal_exact_checks << ",\"primal_ms\":" << primal_ms << ",\"primal_found\":" << (primal_found?"true":"false")
                << ",\"failures\":" << statistics.fail << ",\"propagations\":" << statistics.propagate
                << ",\"peak_rss_kb\":" << rss << ",\"objective\":";
      if (best.empty()) std::cout << "null"; else std::cout << best_cost;
      std::cout << ",\"assignment\":[";
      for (std::size_t j=0;j<best.size();++j) std::cout << (j?",":"") << best[j];
      std::cout << "],\"improvements\":[";
      for (std::size_t j=0;j<improvements.size();++j)
        std::cout << (j?",":"") << '[' << improvements[j].first << ',' << improvements[j].second << ']';
      std::cout << "],\"features\":[";for(std::size_t j=0;j<f.size();++j)std::cout<<(j?",":"")<<f[j];std::cout << "]}" << std::endl;
    }
  } catch (const std::exception& e) {std::cerr << e.what() << '\n';return 1;}
}

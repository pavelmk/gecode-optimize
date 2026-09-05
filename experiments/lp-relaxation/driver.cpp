#include <gecode/int.hh>
#include <gecode/minimodel.hh>
#include <gecode/search.hh>
#include <gecode/minimodel/lp-model.hpp>
#ifdef WITH_LP
#include <gecode/minimodel/lp-relaxation.hpp>
#endif
#include <algorithm>
#include <chrono>
#include <fstream>
#include <iostream>
#include <memory>
#include <numeric>
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
#ifdef WITH_LP
  std::shared_ptr<LP::Backend> backend;
#endif
};

class Model : public IntMinimizeSpace {
public:
  IntVarArray x;
  IntVar objective;
  Model(const Instance& p,const Configuration& cfg)
      : x(*this,static_cast<int>(p.model.c.size()),0,1),objective(*this,p.lo,p.hi) {
#ifdef WITH_LP
    if (cfg.backend)
      LP::binary_linear_minimize(*this,x,objective,cfg.backend,
        cfg.mode=="root" ? LP::Frequency::Root : LP::Frequency::EveryNode);
    else
#endif
      LP::post_native(*this,x,objective,p.model);
    if (cfg.warm && !p.incumbent.empty())
      rel(*this,objective,IRT_LE,p.incumbent_cost);
    // The same objective-aware value order and variable rule in both solvers.
    const bool negative=std::all_of(p.model.c.begin(),p.model.c.end(),[](auto c){return c<=0;});
    IntValBranch values=negative ? INT_VAL_MAX() : INT_VAL_MIN();
    if (cfg.branching=="afc") branch(*this,x,INT_VAR_AFC_SIZE_MAX(0.99),values);
    else if (cfg.branching=="size") branch(*this,x,INT_VAR_SIZE_MIN(),values);
    else throw std::runtime_error("Unknown branching policy");
  }
  Model(Model& other):IntMinimizeSpace(other) {x.update(*this,other.x);objective.update(*this,other.objective);}
  Space* copy() override {return new Model(*this);}
  IntVar cost() const override {return objective;}
};

int main(int argc,char** argv) {
  try {
    if (argc!=7) throw std::runtime_error("Usage: driver INPUT none|root|node afc|size LIMIT_MS WARM_START REPEATS");
    Instance input(argv[1]);
    std::string mode=argv[2],branching=argv[3];
    double limit=std::stod(argv[4]);
    bool warm=std::stoi(argv[5])!=0;
    int repeats=std::stoi(argv[6]);
    if ((mode!="none" && mode!="root" && mode!="node") || limit<=0 || repeats<=0)
      throw std::runtime_error("Invalid mode or budget");
#ifndef WITH_LP
    if (mode!="none") throw std::runtime_error("Stock executable has no LP feature");
#endif
    for (int repetition=0;repetition<repeats;++repetition) {
      const auto begin=Clock::now();
      Search::TimeStop stop(limit);
      Configuration cfg; cfg.mode=mode;cfg.branching=branching;cfg.warm=warm;
#ifdef WITH_LP
      if (mode!="none") cfg.backend=std::make_shared<LP::Backend>(input.model);
#endif
      std::vector<int> best;
      int best_cost=0;
      if (warm && !input.incumbent.empty()) {best=input.incumbent;best_cost=input.incumbent_cost;}
      auto root=std::make_unique<Model>(input,cfg);
      const auto constructed=Clock::now();
      Search::Options options;options.threads=1;options.stop=&stop;
      Search::Statistics statistics;
      bool stopped;
      std::vector<std::pair<double,int>> improvements;
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
      double lp_ms=0;
#ifdef WITH_LP
      if (cfg.backend) {
        auto s=cfg.backend->statistics();lp_calls=s.lp_calls;lp_ms=s.lp_ms;
        valid_bounds=s.valid_bounds;rejected=s.rejected;lp_infeasible=s.infeasible_status;
        cfg.backend.reset();
      }
#endif
      const auto finished=Clock::now();
      struct rusage usage;getrusage(RUSAGE_SELF,&usage);
      long rss=usage.ru_maxrss;
#ifdef __APPLE__
      rss/=1024;
#endif
      const char* status=best.empty() ? (stopped?"unknown":"infeasible") : (stopped?"feasible":"optimal");
      std::cout << "{\"status\":\"" << status << "\",\"mode\":\"" << mode << "\",\"branching\":\"" << branching
                << "\",\"stopped\":" << (stopped?"true":"false")
                << ",\"elapsed_ms\":" << std::chrono::duration<double,std::milli>(finished-begin).count()
                << ",\"build_ms\":" << std::chrono::duration<double,std::milli>(constructed-begin).count()
                << ",\"lp_ms\":" << lp_ms << ",\"lp_calls\":" << lp_calls
                << ",\"certified_bounds\":" << valid_bounds << ",\"rejected_bounds\":" << rejected
                << ",\"lp_infeasible_statuses\":" << lp_infeasible << ",\"nodes\":" << statistics.node
                << ",\"failures\":" << statistics.fail << ",\"propagations\":" << statistics.propagate
                << ",\"peak_rss_kb\":" << rss << ",\"objective\":";
      if (best.empty()) std::cout << "null"; else std::cout << best_cost;
      std::cout << ",\"assignment\":[";
      for (std::size_t j=0;j<best.size();++j) std::cout << (j?",":"") << best[j];
      std::cout << "],\"improvements\":[";
      for (std::size_t j=0;j<improvements.size();++j)
        std::cout << (j?",":"") << '[' << improvements[j].first << ',' << improvements[j].second << ']';
      std::cout << "]}" << std::endl;
    }
  } catch (const std::exception& e) {std::cerr << e.what() << '\n';return 1;}
}

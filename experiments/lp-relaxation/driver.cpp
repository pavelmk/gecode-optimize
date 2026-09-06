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
  LP::SparseLinearModel sparse;
  LP::BoundedIntegerModel integer;
  bool use_sparse,use_integer;
  LP::SparseLinearModel& sparse_data() {return use_integer?integer.linear:sparse;}
  const LP::SparseLinearModel& sparse_data() const {return use_integer?integer.linear:sparse;}
  const std::vector<std::int64_t>& costs() const { return use_sparse ? sparse_data().c : model.c; }
  std::vector<int> incumbent;
  int incumbent_cost=0;
  int lo=0,hi=0;
  explicit Instance(const char* path,bool csr=false,bool bounded_integer=false)
    : use_sparse(csr || bounded_integer),use_integer(bounded_integer) {
    std::ifstream f(path);
    int n,m;
    if (!(f>>n>>m) || n<=0 || n>10000 || m<0 || m>10000 || (!use_sparse && 1LL*n*m>10000000))
      throw std::runtime_error("Invalid dimensions");
    auto& csr_model=sparse_data();
    auto& c=use_sparse ? csr_model.c : model.c;
    auto& b=use_sparse ? csr_model.b : model.b;
    c.resize(n); b.resize(m);
    if (use_sparse) csr_model.row_start.reserve(static_cast<std::size_t>(m)+1);
    else model.a.assign(n*m,0);
    for (auto& cost:c) if (!(f>>cost)) throw std::runtime_error("Invalid objective");
    if (use_integer) {
      std::string bounds;
      if (!(f>>bounds) || bounds!="bounds") throw std::runtime_error("Integer input requires bounds followed by n lower/upper pairs");
      integer.lower.resize(n);integer.upper.resize(n);
      for (int j=0;j<n;++j)
        if (!(f>>integer.lower[j]>>integer.upper[j])) throw std::runtime_error("Invalid integral domain endpoints");
    }
    for (int i=0;i<m;++i) {
      int count;
      if (!(f>>b[i]>>count) || count<0 || count>n)
        throw std::runtime_error("Invalid row");
      int previous=-1;
      for (int k=0;k<count;++k) {
        int j; std::int64_t a;
        if (!(f>>j>>a) || j<=previous || j>=n || !a)
          throw std::runtime_error("Invalid coefficient");
        previous=j;
        if (use_sparse) { csr_model.column.push_back(static_cast<std::size_t>(j)); csr_model.a.push_back(a); }
        else model.a[i*n+j]=a;
      }
      if (use_sparse) csr_model.row_start.push_back(csr_model.a.size());
    }
    if (use_integer) {
      LP::validate_integer_model(integer);
      for (int j=0;j<n;++j) {
        const auto a=c[j]*integer.lower[j],b=c[j]*integer.upper[j];
        lo+=static_cast<int>(std::min(a,b));hi+=static_cast<int>(std::max(a,b));
      }
    } else {
      if (use_sparse) LP::validate_model(csr_model); else LP::validate_model(model);
      for (auto c:costs()) { if (c<0) lo+=static_cast<int>(c); else hi+=static_cast<int>(c); }
    }
    std::string label;
    int present;
    if (!(f>>label>>present) || label!="incumbent" || (present!=0 && present!=1))
      throw std::runtime_error("Invalid incumbent trailer");
    if (present) {
      incumbent.resize(n);
      for (int j=0;j<n;++j)
        if (!(f>>incumbent[j]) || (use_integer ?
             (incumbent[j]<integer.lower[j] || incumbent[j]>integer.upper[j]) :
             (incumbent[j]!=0 && incumbent[j]!=1))) throw std::runtime_error("Incumbent violates variable domain");
      for (int i=0;i<m;++i) {
        std::int64_t lhs=0;
        if (use_sparse) {
          for (auto k=csr_model.row_start[i];k<csr_model.row_start[i+1];++k)
            lhs+=csr_model.a[k]*incumbent[csr_model.column[k]];
        } else for (int j=0;j<n;++j) lhs+=model.a[i*n+j]*incumbent[j];
        if (lhs<b[i]) throw std::runtime_error("Incumbent violates a constraint");
      }
      for (int j=0;j<n;++j) incumbent_cost+=static_cast<int>(costs()[j])*incumbent[j];
    }
    if (use_integer && (f>>std::ws).peek()!=std::char_traits<char>::eof())
      throw std::runtime_error("Unexpected trailing integer model content");
  }
};

struct Configuration {
  std::string mode,branching;
  bool warm;
#ifdef WITH_LP
  std::shared_ptr<LP::SparseBackend> backend;
  std::shared_ptr<LP::BoundedIntegerBackend> integer_backend;
#endif
};

class Model : public IntMinimizeSpace {
public:
  IntVarArray x;
  IntVar objective;
  Model(const Instance& p,const Configuration& cfg)
      : x(*this,static_cast<int>(p.costs().size())),objective(*this,p.lo,p.hi) {
    for (int j=0;j<x.size();++j)
      x[j]=IntVar(*this,p.use_integer?static_cast<int>(p.integer.lower[j]):0,
                       p.use_integer?static_cast<int>(p.integer.upper[j]):1);
#ifdef WITH_LP
    if (cfg.integer_backend) {
      LP::IntegerOptions policy;
      policy.frequency=cfg.mode=="root" || cfg.mode=="root-tight" ? LP::Frequency::Root : LP::Frequency::EveryNode;
      policy.bound_tightening=cfg.mode=="root-tight" || cfg.mode=="node-tight";
      LP::integer_linear_minimize(*this,x,objective,cfg.integer_backend,policy);
    } else if (cfg.backend)
      LP::binary_linear_minimize(*this,x,objective,cfg.backend,
        cfg.mode=="root" ? LP::Frequency::Root : LP::Frequency::EveryNode);
    else
#endif
    {
      if (p.use_integer) LP::post_native_integer(*this,x,objective,p.integer);
      else if (p.use_sparse) LP::post_native(*this,x,objective,p.sparse_data());
      else LP::post_native(*this,x,objective,p.model);
    }
    if (cfg.warm && !p.incumbent.empty())
      rel(*this,objective,IRT_LE,p.incumbent_cost);
    // The same objective-aware value order and variable rule in both solvers.
    const bool negative=std::all_of(p.costs().begin(),p.costs().end(),[](auto c){return c<=0;});
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
    if (argc!=7 && argc!=8) throw std::runtime_error("Usage: driver INPUT none|root|node|root-tight|node-tight afc|size LIMIT_MS WARM_START REPEATS [--sparse|--integer]");
    const std::string representation=argc==8?argv[7]:"";
    if (!representation.empty() && representation!="--sparse" && representation!="--integer")
      throw std::runtime_error("Unknown model option; expected --sparse or --integer");
    Instance input(argv[1],representation=="--sparse",representation=="--integer");
    std::string mode=argv[2],branching=argv[3];
    double limit=std::stod(argv[4]);
    bool warm=std::stoi(argv[5])!=0;
    int repeats=std::stoi(argv[6]);
    if ((mode!="none" && mode!="root" && mode!="node" &&
         !(input.use_integer && (mode=="root-tight" || mode=="node-tight"))) || limit<=0 || repeats<=0)
      throw std::runtime_error("Invalid mode or budget");
#ifndef WITH_LP
    if (mode!="none") throw std::runtime_error("Stock executable has no LP feature");
#endif
    for (int repetition=0;repetition<repeats;++repetition) {
      const auto begin=Clock::now();
      Search::TimeStop stop(limit);
      Configuration cfg; cfg.mode=mode;cfg.branching=branching;cfg.warm=warm;
#ifdef WITH_LP
      if (mode!="none") {
        if (input.use_integer) cfg.integer_backend=std::make_shared<LP::BoundedIntegerBackend>(input.integer);
        else if (input.use_sparse) cfg.backend=std::make_shared<LP::SparseBackend>(input.sparse_data());
        else cfg.backend=std::make_shared<LP::Backend>(input.model);
      }
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
      if (cfg.integer_backend) {
        auto s=cfg.integer_backend->statistics();lp_calls=s.lp_calls;lp_ms=s.lp_ms;
        valid_bounds=s.valid_bounds;rejected=s.rejected;lp_infeasible=s.infeasible_status;
        cfg.integer_backend.reset();
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
                << "\",\"matrix_storage\":\"" << (input.use_sparse?"csr":"dense")
                << "\",\"variable_domain\":\"" << (input.use_integer?"bounded-integer":"binary")
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

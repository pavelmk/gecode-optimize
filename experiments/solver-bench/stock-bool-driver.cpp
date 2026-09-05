/* Optional stock-Gecode Boolean representation control. SPDX-License-Identifier: MIT
 *
 * The matrix parser, algebraic features, timing boundary, incumbent treatment
 * and JSON schema follow the adjacent driver.cpp. The deliberate change is
 * BoolVarArray + Boolean linear propagators + BOOL_VAR_AFC_MAX, instead of
 * IntVarArray + integer linear propagators + INT_VAR_AFC_SIZE_MAX. Unassigned
 * binary integer variables all have size two, so the latter's size divisor
 * does not distinguish candidate variables. Propagators/AFC histories can
 * still differ, and that is part of this representation comparison.
 *
 * Build with pristine stock headers/libraries first in the include/link order.
 * lp-model.hpp supplies only the shared data structure and input validator;
 * no LP backend, HiGHS library, new propagator or selected policy is used.
 */
#include <gecode/int.hh>
#include <gecode/minimodel.hh>
#include <gecode/search.hh>
#include <gecode/minimodel/lp-model.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#include <sys/resource.h>

using namespace Gecode;
namespace LP=Gecode::Experimental::LpRelaxation;
using Clock=std::chrono::steady_clock;

struct Instance {
  LP::LinearModel model;
  std::vector<int> incumbent;
  int incumbent_cost=0,lo=0,hi=0;

  // Exact original-matrix validation. The input limits bound each row sum by
  // 10^13, within int64; objective range is checked by validate_model.
  int verify(const std::vector<int>& assignment) const {
    if (assignment.size()!=model.c.size())
      throw std::runtime_error("Wrong witness dimension");
    std::int64_t cost=0;
    for (std::size_t j=0;j<assignment.size();++j) {
      if (assignment[j]!=0 && assignment[j]!=1)
        throw std::runtime_error("Nonbinary witness");
      cost+=model.c[j]*assignment[j];
    }
    for (std::size_t i=0;i<model.b.size();++i) {
      std::int64_t lhs=0;
      for (std::size_t j=0;j<assignment.size();++j)
        lhs+=model.a[i*assignment.size()+j]*assignment[j];
      if (lhs<model.b[i]) throw std::runtime_error("Witness violates original matrix");
    }
    return static_cast<int>(cost);
  }

  explicit Instance(const char* path) {
    std::ifstream f(path);int n,m;
    if (!(f>>n>>m) || n<=0 || n>10000 || m<0 || m>10000 || 1LL*n*m>10000000)
      throw std::runtime_error("Invalid dimensions");
    model.c.resize(n);model.b.resize(m);model.a.assign(n*m,0);
    for (auto& c:model.c) if (!(f>>c)) throw std::runtime_error("Invalid objective");
    for (int i=0;i<m;++i) {
      int count;
      if (!(f>>model.b[i]>>count) || count<0 || count>n)
        throw std::runtime_error("Invalid row");
      int previous=-1;
      for (int k=0;k<count;++k) {
        int j;std::int64_t a;
        if (!(f>>j>>a) || j<=previous || j>=n || !a)
          throw std::runtime_error("Invalid coefficient");
        previous=j;model.a[i*n+j]=a;
      }
    }
    LP::validate_model(model);
    for (auto c:model.c) {if(c<0)lo+=static_cast<int>(c);else hi+=static_cast<int>(c);}
    std::string label;int present;
    if (!(f>>label>>present) || label!="incumbent" || (present!=0 && present!=1))
      throw std::runtime_error("Invalid incumbent trailer");
    if (present) {
      incumbent.resize(n);
      for (int& value:incumbent) if (!(f>>value)) throw std::runtime_error("Invalid incumbent bit");
      incumbent_cost=verify(incumbent);
    }
    std::string extra;
    if (f>>extra) throw std::runtime_error("Trailing input");
  }
};

// Same original-matrix features and timed work as driver.cpp; no selector.
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
  BoolVarArray x;
  IntVar objective;
  const LP::LinearModel* matrix;
  Model(const Instance& p,bool warm)
      :x(*this,static_cast<int>(p.model.c.size()),0,1),
       objective(*this,p.lo,p.hi),matrix(&p.model) {
    // Match the second, timed validation in the shared post_native helper.
    LP::validate_model(*matrix);
    for (std::size_t i=0;i<matrix->b.size();++i) {
      IntArgs coefficients;BoolVarArgs variables;
      for (int j=0;j<x.size();++j) if (matrix->a[i*x.size()+j]) {
        coefficients<<static_cast<int>(matrix->a[i*x.size()+j]);variables<<x[j];
      }
      linear(*this,coefficients,variables,IRT_GQ,static_cast<int>(matrix->b[i]),IPL_BND);
    }
    IntArgs costs(x.size());
    for (int j=0;j<x.size();++j) costs[j]=static_cast<int>(matrix->c[j]);
    linear(*this,costs,x,IRT_EQ,objective,IPL_BND);
    if (warm && !p.incumbent.empty()) rel(*this,objective,IRT_LE,p.incumbent_cost);
    BoolValBranch values=BOOL_VAL([](const Space& home,BoolVar variable,int j) {
      return static_cast<const Model&>(home).matrix->c[j]<0?variable.max():variable.min();
    });
    branch(*this,x,BOOL_VAR_AFC_MAX(0.99),values);
  }
  Model(Model& other):IntMinimizeSpace(other),matrix(other.matrix) {
    x.update(*this,other.x);objective.update(*this,other.objective);
  }
  Space* copy() override {return new Model(*this);}
  IntVar cost() const override {return objective;}
};

int main(int argc,char** argv) {
  try {
    if (argc!=7) throw std::runtime_error("Usage: stock-bool INPUT native afc LIMIT_MS WARM_START REPEATS");
    Instance input(argv[1]);const std::string mode=argv[2],branching=argv[3];
    const double limit=std::stod(argv[4]);const int warm_flag=std::stoi(argv[5]),repeats=std::stoi(argv[6]);
    if (mode!="native" || branching!="afc" || !std::isfinite(limit) || limit<=0 || limit>86400000 ||
        (warm_flag!=0 && warm_flag!=1) || repeats<=0)
      throw std::runtime_error("Invalid stock Boolean configuration");
    const bool warm=warm_flag!=0;
    for (int repetition=0;repetition<repeats;++repetition) {
      const auto begin=Clock::now();Search::TimeStop stop(limit);
      const auto f=features(input.model);
      std::vector<int> best;int best_cost=0;
      if (warm && !input.incumbent.empty()) {best=input.incumbent;best_cost=input.incumbent_cost;}
      std::vector<std::pair<double,int>> improvements;
      auto root=std::make_unique<Model>(input,warm);const auto constructed=Clock::now();
      Search::Options options;options.threads=1;options.stop=&stop;
      Search::Statistics statistics;bool stopped;
      {
        BAB<Model> engine(root.get(),options);root.reset();
        while (Model* solution=engine.next()) {
          best.resize(solution->x.size());
          for (int j=0;j<solution->x.size();++j) best[j]=solution->x[j].val();
          best_cost=solution->objective.val();delete solution;
          improvements.emplace_back(std::chrono::duration<double,std::milli>(Clock::now()-begin).count(),best_cost);
        }
        statistics=engine.statistics();stopped=engine.stopped();
      }
      const auto finished=Clock::now();
      // Validation is outside solver time, matching the shared runner's policy.
      if (!best.empty() && input.verify(best)!=best_cost)
        throw std::runtime_error("Returned objective differs from exact original model");
      struct rusage usage;getrusage(RUSAGE_SELF,&usage);long rss=usage.ru_maxrss;
#ifdef __APPLE__
      rss/=1024;
#endif
      const char* status=best.empty()?(stopped?"unknown":"infeasible"):(stopped?"feasible":"optimal");
      std::cout<<"{\"status\":\""<<status<<"\",\"mode\":\"native\",\"requested_mode\":\"native\",\"branching\":\"afc\""
        <<",\"representation\":\"BoolVarArray/Boolean linear\",\"stopped\":"<<(stopped?"true":"false")
        <<",\"elapsed_ms\":"<<std::chrono::duration<double,std::milli>(finished-begin).count()
        <<",\"build_ms\":"<<std::chrono::duration<double,std::milli>(constructed-begin).count()
        <<",\"pre_proof_ms\":"<<std::chrono::duration<double,std::milli>(constructed-begin).count()
        <<",\"lp_ms\":0,\"lp_calls\":0,\"certified_bounds\":0,\"rejected_bounds\":0,\"lp_infeasible_statuses\":0"
        <<",\"nodes\":"<<statistics.node<<",\"conditional_checks\":0,\"variable_fixings\":0"
        <<",\"cuts\":0,\"clique_cuts\":0,\"cover_cuts\":0,\"gcd_rows\":0,\"heuristic_nodes\":0,\"neighborhoods\":0"
        <<",\"total_nodes\":"<<statistics.node
        <<",\"primal_lp_calls\":0,\"primal_exact_checks\":0,\"primal_ms\":0,\"primal_found\":false"
        <<",\"failures\":"<<statistics.fail<<",\"propagations\":"<<statistics.propagate
        <<",\"peak_rss_kb\":"<<rss<<",\"objective\":";
      if(best.empty())std::cout<<"null";else std::cout<<best_cost;
      std::cout<<",\"assignment\":[";
      for(std::size_t j=0;j<best.size();++j)std::cout<<(j?",":"")<<best[j];
      std::cout<<"],\"improvements\":[";
      for(std::size_t j=0;j<improvements.size();++j)
        std::cout<<(j?",":"")<<'['<<improvements[j].first<<','<<improvements[j].second<<']';
      std::cout<<"],\"features\":[";
      for(std::size_t j=0;j<f.size();++j)std::cout<<(j?",":"")<<f[j];
      std::cout<<"]}"<<std::endl;
    }
  } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}

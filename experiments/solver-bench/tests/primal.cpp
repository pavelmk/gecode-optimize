// Exact witness acceptance and bounded LP-only primal generation.
#include <gecode/minimodel/lp-primal.hpp>
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <limits>
#include <random>
#include <set>
#include <stdexcept>
#include <vector>

namespace LP=Gecode::Experimental::LpRelaxation;
namespace P=LP::Primal;
using I=std::int64_t;

static void require(bool value,const char* message) {
  if (!value) throw std::runtime_error(message);
}

static std::set<std::vector<int>> enumerate(const LP::LinearModel& model,
                                          std::optional<I> cutoff=std::nullopt) {
  const auto n=model.c.size();
  std::set<std::vector<int>> feasible;
  for (unsigned mask=0;mask<(1U<<n);++mask) {
    std::vector<int> point(n);
    for (std::size_t j=0;j<n;++j) point[j]=(mask>>j)&1U;
    bool valid=true;
    for (std::size_t i=0;i<model.b.size();++i) {
      I activity=0;
      for (std::size_t j=0;j<n;++j) activity+=model.a[i*n+j]*point[j];
      if (activity<model.b[i]) valid=false;
    }
    I cost=0;
    for (std::size_t j=0;j<n;++j) cost+=model.c[j]*point[j];
    if (valid && (!cutoff || cost<*cutoff)) feasible.insert(point);
  }
  return feasible;
}

static void check_verifier() {
  I out=73;
  require(!P::verify({{1},{1},{1}},{2},out) && out==73,"nonbinary witness accepted");
  require(!P::verify({{1},{1},{1}},{},out) && out==73,"wrong witness dimension accepted");
  require(!P::verify({{1,2},{1},{1}},{1},out) && out==73,"wrong matrix dimension accepted");
  require(!P::verify({{1},{1},{1}},{0},out) && out==73,"infeasible witness accepted");
  const I big=std::numeric_limits<I>::max(),small=std::numeric_limits<I>::min();
  require(!P::verify({{big,1},{0},{0,0}},{1,1},out) && out==73,"positive row overflow accepted");
  require(!P::verify({{small,-1},{small},{0,0}},{1,1},out) && out==73,"negative row overflow accepted");
  require(!P::verify({{},{},{big,1}},{1,1},out) && out==73,"positive cost overflow accepted");
  require(!P::verify({{},{},{small,-1}},{1,1},out) && out==73,"negative cost overflow accepted");
  require(P::verify({{big,small},{-1},{big,small}},{1,1},out) && out==-1,"valid extreme arithmetic rejected");
}

static void check_special_cases() {
  P::Options options;options.wall_budget_ms=2000;
  auto result=P::generate({{},{},{}},options);
  require(result.found && result.assignment.empty() && result.cost==0 && result.lp_calls==0,"empty feasible model");
  result=P::generate({{},{1},{}},options);
  require(!result.found && result.lp_calls==0,"empty infeasible model");
  result=P::generate({{},{},{-5,3,0}},options);
  require(result.found && result.assignment==std::vector<int>({1,0,0}) && result.cost==-5 && !result.lp_calls,"unconstrained sign minimization");
  options.strict_cutoff=-5;result=P::generate({{},{},{-5,3,0}},options);
  require(!result.found && !result.lp_calls,"strict natural lower cutoff");
  options.strict_cutoff=std::numeric_limits<I>::min();
  require(!P::generate({{},{},{-5,3,0}},options).found,"cutoff INT64_MIN");
  options.strict_cutoff=std::numeric_limits<I>::max();
  require(P::generate({{},{},{-5,3,0}},options).found,"cutoff INT64_MAX");
  options.strict_cutoff.reset();options.wall_budget_ms=0;
  require(!P::generate({{},{},{-1}},options).found,"zero wall budget");
  options.wall_budget_ms=2000;options.max_lp_calls=0;
  require(!P::generate({{},{},{-1}},options).found,"zero call budget");
  options.max_lp_calls=8;
  for (double budget:{-1.0,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
    options.wall_budget_ms=budget;bool threw=false;
    try { (void)P::generate({{},{},{-1}},options); } catch(const std::invalid_argument&) { threw=true; }
    require(threw,"invalid wall budget accepted");
  }
  options.wall_budget_ms=2000;
  bool threw=false;
  try { (void)P::generate({{1,2},{1},{1}},options); } catch(const std::invalid_argument&) { threw=true; }
  require(threw,"bad model accepted");
  threw=false;
  try { (void)P::generate({{},{},{1000000001}},options); } catch(const std::invalid_argument&) { threw=true; }
  require(threw,"excess coefficient accepted");

  // Integral assignment relaxation: each row and column sums to one.
  LP::LinearModel assignment{{1,1,0,0,-1,-1,0,0,0,0,1,1,0,0,-1,-1,
                             1,0,1,0,-1,0,-1,0,0,1,0,1,0,-1,0,-1},
                            {1,-1,1,-1,1,-1,1,-1},{1,5,7,2}};
  result=P::generate(assignment,options);
  require(result.found && result.cost==3 && result.lp_calls==1,"integral assignment LP witness");
  options.strict_cutoff=4;result=P::generate(assignment,options);
  require(result.found && result.cost==3,"strict improving assignment witness");
  options.strict_cutoff=3;result=P::generate(assignment,options);
  require(!result.found,"nonimproving assignment accepted");
  options.strict_cutoff.reset();options.max_lp_calls=6;
  const LP::LinearModel parity{{2,-2},{1,-1},{1}}; // LP x=.5, no binary point.
  auto first=P::generate(parity,options),second=P::generate(parity,options);
  require(!first.found && !second.found && first.lp_calls==6 && first.perturbations>0,"cycle perturbation/call cap");
  require(first.lp_calls==second.lp_calls && first.perturbations==second.perturbations && first.exact_checks==second.exact_checks,"fixed-seed deterministic counts");
  require(first.elapsed_ms>=0 && std::isfinite(first.elapsed_ms),"invalid elapsed time");
}

static void check_random() {
  std::mt19937 rng(891013);
  unsigned found=0;
  for (unsigned trial=0;trial<300;++trial) {
    const unsigned n=2+rng()%7,m=rng()%7;
    LP::LinearModel model;model.c.resize(n);model.b.resize(m);model.a.resize(n*m);
    for (auto& value:model.c) value=static_cast<int>(rng()%13)-6;
    for (auto& value:model.a) value=static_cast<int>(rng()%9)-4;
    for (auto& value:model.b) value=static_cast<int>(rng()%13)-6;
    for (auto cutoff:{std::optional<I>{},std::optional<I>{0},std::optional<I>{-7}}) {
      P::Options options;options.wall_budget_ms=2000;options.strict_cutoff=cutoff;
      options.max_lp_calls=1+trial%8;
      const auto oracle=enumerate(model,cutoff);
      const auto result=P::generate(model,options);
      require(result.lp_calls<=options.max_lp_calls,"LP call cap exceeded");
      require(result.exact_checks<=std::max<std::uint64_t>(1,result.lp_calls),"unexpected candidate checks");
      if (result.found) {
        ++found;
        require(oracle.count(result.assignment)==1,"candidate absent from independent exhaustive oracle");
        I cost=0;
        for (unsigned j=0;j<n;++j) cost+=model.c[j]*result.assignment[j];
        require(cost==result.cost,"reported objective mismatch");
      } else {
        require(result.assignment.empty(),"failed heuristic returned assignment");
      }
    }
  }
  std::cout<<"PASS primal exact checker, integral assignment, cutoff/empty/budget/cycle cases; 900 randomized cutoff models, "<<found<<" accepted witnesses independently enumerated\n";
}

int main() {
  try { check_verifier();check_special_cases();check_random(); }
  catch (const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}

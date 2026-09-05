/* Experimental continuous-LP primal candidate generation. SPDX-License-Identifier: MIT */
#ifndef GECODE_MINIMODEL_LP_PRIMAL_HPP
#define GECODE_MINIMODEL_LP_PRIMAL_HPP

#include <Highs.h>
#include <gecode/minimodel/lp-model.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>
#include <optional>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace Gecode { namespace Experimental { namespace LpRelaxation { namespace Primal {

struct Options {
  unsigned int max_lp_calls=8;
  double wall_budget_ms=50.0;
  unsigned int seed=9173;
  /// If supplied, an accepted candidate must have strictly smaller cost.
  std::optional<std::int64_t> strict_cutoff;
};

struct CandidateResult {
  std::vector<int> assignment;
  std::int64_t cost=0;
  bool found=false;
  std::uint64_t lp_calls=0, exact_checks=0, rejected_candidates=0;
  std::uint64_t perturbations=0, lp_errors=0;
  double elapsed_ms=0.0;
};
using Result=CandidateResult;

namespace Detail {
inline bool add(std::int64_t a,std::int64_t b,std::int64_t& out) {
  if ((b>0 && a>std::numeric_limits<std::int64_t>::max()-b) ||
      (b<0 && a<std::numeric_limits<std::int64_t>::min()-b))
    return false;
  out=a+b;
  return true;
}
inline void require_ok(HighsStatus status,const char* operation) {
  if (status!=HighsStatus::kOk)
    throw std::runtime_error(std::string("LP primal: HiGHS ")+operation);
}
} // namespace Detail

/** Exact independent check of a proposed binary witness.
 * No floating-point feasibility tolerance or objective value is trusted.
 * Overflow, malformed dimensions or a nonbinary bit reject the witness;
 * false leaves cost unchanged. This checker never proves infeasibility.
 */
inline bool verify(const LinearModel& model,const std::vector<int>& assignment,
                   std::int64_t& cost) {
  const auto n=model.c.size(),m=model.b.size();
  if (assignment.size()!=n ||
      (n && m>std::numeric_limits<std::size_t>::max()/n) || model.a.size()!=m*n)
    return false;
  for (int value:assignment)
    if (value!=0 && value!=1) return false;
  for (std::size_t i=0;i<m;++i) {
    std::int64_t activity=0;
    for (std::size_t j=0;j<n;++j)
      if (assignment[j] && !Detail::add(activity,model.a[i*n+j],activity))
        return false;
    if (activity<model.b[i]) return false;
  }
  std::int64_t exact_cost=0;
  for (std::size_t j=0;j<n;++j)
    if (assignment[j] && !Detail::add(exact_cost,model.c[j],exact_cost))
      return false;
  cost=exact_cost;
  return true;
}

/** Bounded rounding/projection heuristic in an independent LP workspace.
 * First solve the original objective; subsequent LPs minimize L1 distance
 * to a binary point, with deterministic cycle perturbations. For a binary
 * target t the variable part of this distance is (1-2t)*x, so no auxiliary
 * integer variables or HiGHS MIP solve are needed. A valid original-model
 * witness is the only useful output; failure conveys no bound or proof.
 * The wall budget is soft: it is checked between work units, and each LP
 * receives the remaining allowance (at most 20ms and 1000 iterations).
 * elapsed_ms includes model validation, construction and workspace teardown.
 */
inline CandidateResult generate(const LinearModel& model,const Options& options=Options()) {
  using Clock=std::chrono::steady_clock;
  const auto begin=Clock::now();
  CandidateResult result;
  validate_model(model);
  if (!std::isfinite(options.wall_budget_ms) || options.wall_budget_ms<0)
    throw std::invalid_argument("LP primal wall budget must be finite and nonnegative");
  const auto elapsed=[&] {
    return std::chrono::duration<double,std::milli>(Clock::now()-begin).count();
  };
  const auto accept=[&](const std::vector<int>& candidate) {
    ++result.exact_checks;
    std::int64_t value;
    if (!verify(model,candidate,value) ||
        (options.strict_cutoff && value>=*options.strict_cutoff)) {
      ++result.rejected_candidates;
      return false;
    }
    result.assignment=candidate; result.cost=value; result.found=true;
    return true;
  };
  // Scope workspace destruction before computing total elapsed time.
  [&] {
    if (!options.max_lp_calls || elapsed()>=options.wall_budget_ms) return;
    const auto n=model.c.size(),m=model.b.size();
    std::int64_t natural_lower=0,natural_upper=0;
    for (auto c:model.c) {
      auto& value=c<0 ? natural_lower : natural_upper;
      if (!Detail::add(value,c,value))
        throw std::invalid_argument("LP primal objective range overflow");
    }
    if (options.strict_cutoff && *options.strict_cutoff<=natural_lower) return;
    if (!n || !m) {
      std::vector<int> point(n);
      for (std::size_t j=0;j<n;++j) point[j]=model.c[j]<0;
      accept(point);
      return;
    }
    const bool add_cutoff=options.strict_cutoff && *options.strict_cutoff<=natural_upper;
    const auto limit=static_cast<std::size_t>(std::numeric_limits<HighsInt>::max());
    if (n>limit || m>limit-static_cast<std::size_t>(add_cutoff) ||
        model.a.size()>limit || (add_cutoff && n>limit-model.a.size()))
      throw std::invalid_argument("LP primal model exceeds HiGHS index range");

    Highs highs;
    Detail::require_ok(highs.setOptionValue("output_flag",false),"output option");
    Detail::require_ok(highs.setOptionValue("threads",1),"threads option");
    Detail::require_ok(highs.setOptionValue("parallel","off"),"parallel option");
    Detail::require_ok(highs.setOptionValue("solver","simplex"),"solver option");
    Detail::require_ok(highs.setOptionValue("simplex_strategy",1),"simplex strategy");
    Detail::require_ok(highs.setOptionValue("presolve","off"),"presolve option");
    Detail::require_ok(highs.setOptionValue("simplex_iteration_limit",1000),"iteration limit");
    HighsLp lp;
    lp.num_col_=static_cast<HighsInt>(n);
    lp.num_row_=static_cast<HighsInt>(m+add_cutoff);
    lp.sense_=ObjSense::kMinimize;
    lp.col_cost_.assign(model.c.begin(),model.c.end());
    lp.col_lower_.assign(n,0.0); lp.col_upper_.assign(n,1.0);
    lp.row_lower_.assign(model.b.begin(),model.b.end());
    lp.row_upper_.assign(m,kHighsInf);
    lp.a_matrix_.format_=MatrixFormat::kRowwise;
    lp.a_matrix_.num_col_=lp.num_col_; lp.a_matrix_.num_row_=lp.num_row_;
    lp.a_matrix_.start_.assign(1,0);
    for (std::size_t i=0;i<m;++i) {
      for (std::size_t j=0;j<n;++j)
        if (model.a[i*n+j]) {
          lp.a_matrix_.index_.push_back(static_cast<HighsInt>(j));
          lp.a_matrix_.value_.push_back(static_cast<double>(model.a[i*n+j]));
        }
      lp.a_matrix_.start_.push_back(static_cast<HighsInt>(lp.a_matrix_.value_.size()));
    }
    if (add_cutoff) {
      lp.row_lower_.push_back(-kHighsInf);
      // cutoff>natural_lower already checked, hence subtraction is safe.
      lp.row_upper_.push_back(static_cast<double>(*options.strict_cutoff-1));
      for (std::size_t j=0;j<n;++j)
        if (model.c[j]) {
          lp.a_matrix_.index_.push_back(static_cast<HighsInt>(j));
          lp.a_matrix_.value_.push_back(static_cast<double>(model.c[j]));
        }
      lp.a_matrix_.start_.push_back(static_cast<HighsInt>(lp.a_matrix_.value_.size()));
    }
    // integrality_ remains empty: every optimization below is continuous.
    Detail::require_ok(highs.passModel(std::move(lp)),"model construction");
    std::mt19937 random(options.seed);
    std::set<std::vector<int>> seen;
    std::vector<double> projection_cost(n);
    for (unsigned call=0;call<options.max_lp_calls;++call) {
      const double remaining=options.wall_budget_ms-elapsed();
      if (remaining<=0) break;
      Detail::require_ok(highs.setOptionValue("time_limit",highs.getRunTime()+
                        std::min(20.0,remaining)/1000.0),"time limit");
      ++result.lp_calls;
      const auto status=highs.run();
      const auto& solution=highs.getSolution();
      if (status==HighsStatus::kError) { ++result.lp_errors; break; }
      if (!solution.value_valid || solution.col_value.size()!=n) break;
      std::vector<int> point(n);
      for (std::size_t j=0;j<n;++j) {
        const double value=solution.col_value[j];
        if (!std::isfinite(value)) { ++result.lp_errors; return; }
        point[j]=value>0.5 || (value==0.5 && model.c[j]<0);
      }
      if (accept(point)) break;
      if (elapsed()>=options.wall_budget_ms || call+1==options.max_lp_calls) break;
      if (!seen.insert(point).second) {
        ++result.perturbations;
        const std::size_t count=std::min<std::size_t>(n,1+(result.perturbations-1)%3);
        std::set<std::size_t> flipped;
        for (std::size_t k=0;k<count;++k) {
          auto j=static_cast<std::size_t>(random())%n;
          while (flipped.count(j)) j=(j+1)%n;
          flipped.insert(j); point[j]=1-point[j];
        }
      }
      for (std::size_t j=0;j<n;++j) projection_cost[j]=point[j] ? -1.0 : 1.0;
      Detail::require_ok(highs.changeColsCost(0,static_cast<HighsInt>(n)-1,
                                           projection_cost.data()),"projection costs");
    }
  }();
  result.elapsed_ms=elapsed();
  return result;
}

}}}} // namespace Gecode::Experimental::LpRelaxation::Primal
#endif

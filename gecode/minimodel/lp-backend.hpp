/* Optional continuous-LP backend for certified Gecode propagation.
 *
 * HiGHS proposes row multipliers. Only the separate exact certificate
 * checker decides whether a lower bound may enter the constraint solver.
 */

#ifndef __GECODE_MINIMODEL_LP_BACKEND_HPP__
#define __GECODE_MINIMODEL_LP_BACKEND_HPP__

#include <Highs.h>
#include <gecode/minimodel/lp-certificate.hpp>
#include <gecode/minimodel/lp-model.hpp>

#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace Gecode { namespace Experimental { namespace LpRelaxation {

  struct BoundResult {
    bool valid = false;
    std::int64_t lower_bound = 0;
    /// Diagnostic only: never rounded or used to prune the CP search.
    double lp_objective = std::numeric_limits<double>::quiet_NaN();
    /// Optional exact residual data for conditional binary bounds.
    std::shared_ptr<const LpCertificate::Certificate> certificate;
  };

  struct Stats {
    std::uint64_t lp_calls = 0;
    double lp_ms = 0.0;
    std::uint64_t valid_bounds = 0;
    std::uint64_t rejected = 0;
    /// Floating-point infeasibility reports, ignored for CP pruning.
    std::uint64_t infeasible_status = 0;
    std::uint64_t certificate_evaluations = 0;
    std::uint64_t conditional_checks = 0;
    std::uint64_t variable_fixings = 0;
  };

  /**
   * Shared, serialized workspace for the descendants of one CP model.
   *
   * Each call replaces every variable bound, including bounds loosened
   * when search revisits a sibling. The previous simplex basis is merely
   * a hot start, and is never treated as a certificate for another node.
   * This object is deliberately not copied with Gecode spaces.
   */
  class Backend {
  public:
    const LinearModel model;

  private:
    mutable std::mutex mutex_;
    Highs highs_;
    Stats stats_;
    std::vector<double> lower_, upper_;

    static void require_ok(HighsStatus status, const char* operation) {
      if (status != HighsStatus::kOk)
        throw std::runtime_error(std::string("LP backend: HiGHS ") + operation);
    }

    void validate_model() const {
      const std::size_t n = model.c.size(), m = model.b.size();
      const std::size_t limit =
        static_cast<std::size_t>(std::numeric_limits<HighsInt>::max());
      if ((n > limit) || (m > limit) ||
          ((m != 0) && (n > std::numeric_limits<std::size_t>::max()/m)) ||
          (model.a.size() != m*n) || (model.a.size() > limit))
        throw std::invalid_argument("LP backend: invalid dense dimensions");
      // These integers are represented exactly as doubles in the LP.
      // Restrict the prototype's numerical range; the certificate still
      // checks every arithmetic operation independently.
      for (const auto* values : {&model.a, &model.b, &model.c})
        for (std::int64_t value : *values)
          if ((value < -1000000000LL) || (value > 1000000000LL))
            throw std::invalid_argument("LP backend: coefficient exceeds 1e9");
    }

  public:
    explicit Backend(LinearModel input) : model(std::move(input)) {
      validate_model();
      require_ok(highs_.setOptionValue("output_flag", false), "output option");
      require_ok(highs_.setOptionValue("threads", 1), "threads option");
      require_ok(highs_.setOptionValue("parallel", "off"), "parallel option");
      require_ok(highs_.setOptionValue("solver", "simplex"), "solver option");
      require_ok(highs_.setOptionValue("simplex_strategy", 1), "simplex strategy");
      require_ok(highs_.setOptionValue("presolve", "off"), "presolve option");
      require_ok(highs_.setOptionValue("simplex_iteration_limit", 10000),
                 "iteration limit");

      const std::size_t n = model.c.size(), m = model.b.size();
      lower_.assign(n, 0.0);
      upper_.assign(n, 1.0);
      if ((n == 0) || (m == 0))
        return; // Empty boxes/row sets are certified without an LP call.

      HighsLp lp;
      lp.num_col_ = static_cast<HighsInt>(n);
      lp.num_row_ = static_cast<HighsInt>(m);
      lp.sense_ = ObjSense::kMinimize;
      lp.col_cost_.assign(model.c.begin(), model.c.end());
      lp.col_lower_ = lower_;
      lp.col_upper_ = upper_;
      lp.row_lower_.assign(model.b.begin(), model.b.end());
      lp.row_upper_.assign(m, kHighsInf);
      lp.a_matrix_.format_ = MatrixFormat::kRowwise;
      lp.a_matrix_.num_col_ = lp.num_col_;
      lp.a_matrix_.num_row_ = lp.num_row_;
      lp.a_matrix_.start_.reserve(m+1);
      // HiGHS already initializes start_ with a zero; replace it rather
      // than appending another empty first row.
      lp.a_matrix_.start_.assign(1, 0);
      for (std::size_t i=0; i<m; ++i) {
        for (std::size_t j=0; j<n; ++j) {
          const std::int64_t value = model.a[i*n+j];
          if (value != 0) {
            lp.a_matrix_.index_.push_back(static_cast<HighsInt>(j));
            lp.a_matrix_.value_.push_back(static_cast<double>(value));
          }
        }
        lp.a_matrix_.start_.push_back(
          static_cast<HighsInt>(lp.a_matrix_.value_.size()));
      }
      // integrality_ remains empty: HiGHS only solves continuous LPs.
      require_ok(highs_.passModel(std::move(lp)), "model construction");
    }

    Backend(const Backend&) = delete;
    Backend& operator=(const Backend&) = delete;

    BoundResult bound(const std::vector<std::int64_t>& lower,
                      const std::vector<std::int64_t>& upper,
                      bool retain_certificate=false) {
      std::lock_guard<std::mutex> lock(mutex_);
      BoundResult result;
      const std::size_t n = model.c.size(), m = model.b.size();
      if ((lower.size() != n) || (upper.size() != n)) {
        ++stats_.rejected;
        return result;
      }
      for (std::size_t j=0; j<n; ++j) {
        if ((lower[j] < 0) || (upper[j] > 1) || (lower[j] > upper[j])) {
          ++stats_.rejected;
          return result;
        }
        lower_[j] = static_cast<double>(lower[j]);
        upper_[j] = static_cast<double>(upper[j]);
      }

      std::vector<double> duals(m, 0.0);
      if ((n != 0) && (m != 0)) {
        using Clock = std::chrono::steady_clock;
        const auto start = Clock::now();
        // HiGHS accumulates run time across reoptimizations. Add this
        // call's allowance to the already consumed run time.
        HighsStatus status = highs_.setOptionValue(
          "time_limit", highs_.getRunTime()+0.2);
        bool ran = false;
        if (status == HighsStatus::kOk)
          status = highs_.changeColsBounds(
            0, static_cast<HighsInt>(n)-1, lower_.data(), upper_.data());
        if (status == HighsStatus::kOk) {
          ++stats_.lp_calls;
          ran = true;
          status = highs_.run();
        }
        stats_.lp_ms += std::chrono::duration<double,std::milli>(
          Clock::now()-start).count();
        if (ran && (highs_.getModelStatus() == HighsModelStatus::kInfeasible))
          ++stats_.infeasible_status;
        const HighsSolution& solution = highs_.getSolution();
        if (!ran || (status == HighsStatus::kError) || !solution.dual_valid ||
            (solution.row_dual.size() != m)) {
          ++stats_.rejected;
          return result;
        }
        for (double dual : solution.row_dual)
          if (!std::isfinite(dual)) {
            ++stats_.rejected;
            return result;
          }
        duals = solution.row_dual;
        const HighsInfo& info = highs_.getInfo();
        if (info.valid && std::isfinite(info.objective_function_value))
          result.lp_objective = info.objective_function_value;
      }

      if (retain_certificate) {
        auto certificate=std::make_shared<LpCertificate::Certificate>();
        result.valid=LpCertificate::prepare(model.a,model.b,model.c,duals,*certificate) &&
          certificate->lower_bound(lower,upper,result.lower_bound);
        if (result.valid)
          result.certificate=std::move(certificate);
      } else {
        // Preserve the original bound-only path unless explicitly requested.
        result.valid = LpCertificate::lower_bound(
          model.a, model.b, model.c, lower, upper, duals, result.lower_bound);
      }
      if (result.valid)
        ++stats_.valid_bounds;
      else
        ++stats_.rejected;
      return result;
    }

    void record_filtering(std::uint64_t conditional_checks,
                          std::uint64_t variable_fixings) {
      std::lock_guard<std::mutex> lock(mutex_);
      ++stats_.certificate_evaluations;
      stats_.conditional_checks+=conditional_checks;
      stats_.variable_fixings+=variable_fixings;
    }

    Stats statistics() const {
      std::lock_guard<std::mutex> lock(mutex_);
      return stats_;
    }
  };

}}}

#endif

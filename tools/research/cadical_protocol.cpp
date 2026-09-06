/* W10 interface experiment. Not linked into Gecode or installed.
 * An independently enumerated signed cardinality constraint exercises IPASIR-UP.
 * This bounded fixture deliberately uses fixed-capacity callback storage.
 */
#include "cadical.hpp"
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <vector>

#ifdef NDEBUG
#error "This protocol experiment requires assertions"
#endif

namespace {
constexpr int capacity = 8;
struct Clause {
  std::array<int, capacity + 1> literals{};
  std::size_t size = 0;
  void push(int literal) { assert(size < literals.size()); literals[size++] = literal; }
};
int variable(int literal) { assert(literal && literal != INT32_MIN); return literal < 0 ? -literal : literal; }
bool holds(int literal, unsigned assignment) {
  const bool value = (assignment & (1u << (variable(literal) - 1))) != 0;
  return literal > 0 ? value : !value;
}
bool holds(const Clause& clause, unsigned assignment) {
  for (std::size_t i = 0; i < clause.size; ++i)
    if (holds(clause.literals[i], assignment)) return true;
  return false;
}
struct Counts {
  std::uint64_t assignments = 0, decisions = 0, backtracks = 0;
  std::uint64_t propagations = 0, reason_streams = 0, external_clauses = 0;
  std::uint64_t checked_models = 0, rejected_models = 0, checked_lemmas = 0;
  std::uint64_t nonchronological_backtracks = 0, delayed_reasons = 0;
  Counts& operator+=(const Counts& b) {
    assignments += b.assignments; decisions += b.decisions; backtracks += b.backtracks;
    propagations += b.propagations; reason_streams += b.reason_streams;
    external_clauses += b.external_clauses; checked_models += b.checked_models;
    rejected_models += b.rejected_models; checked_lemmas += b.checked_lemmas;
    nonchronological_backtracks += b.nonchronological_backtracks;
    delayed_reasons += b.delayed_reasons; return *this;
  }
};

class Cardinality final : public CaDiCaL::ExternalPropagator {
  CaDiCaL::Solver& solver_;
  int n_, limit_;
  std::array<int, capacity> terms_{};
  std::array<int, capacity + 1> values_{};
  std::array<std::size_t, capacity + 1> levels_{};
  std::array<Clause, 2 * capacity + 1> reasons_{};
  std::array<std::uint64_t, 2 * capacity + 1> reason_events_{};
  std::size_t level_ = 0, reason_cursor_ = 0, clause_cursor_ = 0;
  int streaming_literal_ = 0;
  std::uint64_t event_ = 0;
  Clause pending_;
  bool has_pending_ = false;
  int value(int lit) const { const auto v = values_[variable(lit)]; return lit > 0 ? v : -v; }
  std::size_t key(int lit) const { return static_cast<std::size_t>(lit + capacity); }
  void check_lemma(const Clause& clause) {
    // The checker enumerates the original external constraint. It does not
    // inspect the callback trail or trust the clause-generation arithmetic.
    for (unsigned a = 0; a < (1u << n_); ++a)
      if (satisfied(a)) assert(holds(clause, a));
    ++counts.checked_lemmas;
  }
  Clause true_prefix(int count) const {
    Clause clause;
    for (int i = 0; i < n_ && count; ++i)
      if (value(terms_[i]) > 0) { clause.push(-terms_[i]); --count; }
    assert(count == 0); return clause;
  }
public:
  Counts counts;
  Cardinality(CaDiCaL::Solver& solver, int n, int limit, unsigned negative, bool lazy)
    : solver_(solver), n_(n), limit_(limit) {
    assert(n > 0 && n <= capacity && limit >= 0 && limit <= n);
    is_lazy = lazy;
    are_reasons_forgettable = false; // Explicit: header prose and default differ.
    for (int i = 0; i < n; ++i) terms_[i] = (negative & (1u << i)) ? -(i + 1) : i + 1;
    const int last = solver_.declare_more_variables(n);
    assert(last == n); // Each fixture owns a fresh solver and all its variables.
    solver_.connect_external_propagator(this);
    for (int i = 1; i <= n; ++i) solver_.add_observed_var(i);
  }
  ~Cardinality() override { solver_.disconnect_external_propagator(); }
  bool satisfied(unsigned assignment) const {
    int count = 0;
    for (int i = 0; i < n_; ++i) count += holds(terms_[i], assignment);
    return count <= limit_;
  }
  void notify_assignment(const std::vector<int>& literals) override {
    ++event_;
    for (int lit : literals) {
      const int v = variable(lit); assert(v <= n_);
      const int sign = lit > 0 ? 1 : -1;
      assert(!values_[v] || values_[v] == sign);
      if (!values_[v]) { values_[v] = sign; levels_[v] = level_; }
      ++counts.assignments;
    }
  }
  void notify_new_decision_level() override { ++event_; ++level_; ++counts.decisions; }
  void notify_backtrack(std::size_t level) override {
    ++event_; assert(level < level_);
    if (level_ - level > 1) ++counts.nonchronological_backtracks;
    for (int i = 1; i <= n_; ++i) if (values_[i] && levels_[i] > level) values_[i] = 0;
    level_ = level; ++counts.backtracks;
    // Reasons are immutable while assigned and are retained across backtracks.
    // A later propagation of an unassigned literal may replace its old record.
  }
  int cb_decide() override {
    ++event_;
    for (int i = 0; i < n_; ++i) if (!value(terms_[i])) return terms_[i];
    return 0;
  }
  int cb_propagate() override {
    ++event_;
    int count = 0;
    for (int i = 0; i < n_; ++i) count += value(terms_[i]) > 0;
    if (count > limit_) {
      pending_ = true_prefix(limit_ + 1); check_lemma(pending_);
      has_pending_ = true; return 0;
    }
    if (count == limit_) for (int i = 0; i < n_; ++i) if (!value(terms_[i])) {
      const int consequence = -terms_[i];
      auto clause = true_prefix(limit_); clause.push(consequence); check_lemma(clause);
      reasons_[key(consequence)] = clause; reason_events_[key(consequence)] = event_;
      ++counts.propagations; return consequence;
    }
    return 0;
  }
  int cb_add_reason_clause_lit(int propagated) override {
    const auto& reason = reasons_[key(propagated)];
    assert(reason.size && reason.literals[reason.size - 1] == propagated);
    if (!reason_cursor_) {
      streaming_literal_ = propagated; ++counts.reason_streams;
      if (event_ > reason_events_[key(propagated)] + 1) ++counts.delayed_reasons;
    }
    assert(streaming_literal_ == propagated);
    if (reason_cursor_ < reason.size) return reason.literals[reason_cursor_++];
    reason_cursor_ = 0; streaming_literal_ = 0; return 0;
  }
  bool cb_check_found_model(const std::vector<int>& model) override {
    ++event_; ++counts.checked_models;
    unsigned assignment = 0, seen = 0;
    for (int lit : model) {
      const auto v = variable(lit); assert(v <= n_);
      const auto bit = 1u << (v - 1); assert(!(seen & bit)); seen |= bit;
      if (lit > 0) assignment |= bit;
    }
    assert(seen == (1u << n_) - 1);
    if (satisfied(assignment)) return true;
    ++counts.rejected_models;
    pending_ = Clause{};
    for (int i = 0; i < n_ && pending_.size < static_cast<std::size_t>(limit_ + 1); ++i)
      if (holds(terms_[i], assignment)) pending_.push(-terms_[i]);
    assert(pending_.size == static_cast<std::size_t>(limit_ + 1));
    check_lemma(pending_); has_pending_ = true; return false;
  }
  bool cb_has_external_clause(bool& forgettable) override {
    forgettable = false;
    if (has_pending_) { assert(!clause_cursor_); ++counts.external_clauses; }
    return has_pending_;
  }
  int cb_add_external_clause_lit() override {
    assert(has_pending_);
    if (clause_cursor_ < pending_.size) return pending_.literals[clause_cursor_++];
    clause_cursor_ = 0; has_pending_ = false; return 0;
  }
};

std::vector<Clause> formula(int kind) {
  if (!kind) return {};
  if (kind == 1) return {{{{1, 2}}, 2}, {{{-2, 3}}, 2}, {{{-3, 4}}, 2}};
  return {{{{1, 2, 3}}, 3}, {{{1, 2, -3}}, 3},
          {{{1, -2, 3}}, 3}, {{{-1, 2, 4}}, 3}, {{{-4, -2}}, 2}};
}
bool oracle(const Cardinality& external, const std::vector<Clause>& clauses,
            const std::vector<int>& assumptions, unsigned assignment) {
  if (!external.satisfied(assignment)) return false;
  for (const auto& c : clauses) if (!holds(c, assignment)) return false;
  for (int a : assumptions) if (!holds(a, assignment)) return false;
  return true;
}
struct Stop final : CaDiCaL::Terminator {
  bool stopped = true;
  std::uint64_t calls = 0;
  bool terminate() override { ++calls; return stopped; }
};
}

int main() {
  Counts total; std::uint64_t queries = 0, sat = 0, unsat = 0;
  // Reuse a solver across all 3^4 partial assignments to expose stale reason,
  // root-assignment, and failed-assumption lifetime errors. Repeat in reverse.
  for (int chrono : {0, 1}) for (bool lazy : {false, true})
    for (unsigned negative : {0u, 5u, 15u}) for (int limit = 0; limit <= 4; ++limit)
      for (int kind = 0; kind < 3; ++kind) {
        CaDiCaL::Solver solver;
        solver.set("quiet", 1); // A library compiled with -DQUIET has no option.
        assert(solver.set("chrono", chrono));
        Cardinality external(solver, 4, limit, negative, lazy);
        const auto clauses = formula(kind);
        for (const auto& c : clauses) {
          for (std::size_t i = 0; i < c.size; ++i) solver.add(c.literals[i]);
          solver.add(0);
        }
        for (int pass = 0; pass < 2; ++pass) for (int ordinal = 0; ordinal < 81; ++ordinal) {
          int code = pass ? 80 - ordinal : ordinal;
          std::vector<int> assumptions;
          for (int i = 1; i <= 4; ++i) {
            int digit = code % 3; code /= 3;
            if (digit) { assumptions.push_back(digit == 1 ? i : -i); solver.assume(assumptions.back()); }
          }
          bool expected = false;
          for (unsigned a = 0; a < 16; ++a) expected |= oracle(external, clauses, assumptions, a);
          const int result = solver.solve(); ++queries;
          assert(result == (expected ? 10 : 20));
          if (result == 10) {
            ++sat; unsigned a = 0;
            for (int i = 1; i <= 4; ++i) if (solver.val(i) > 0) a |= 1u << (i - 1);
            assert(oracle(external, clauses, assumptions, a));
          } else ++unsat;
        }
        total += external.counts;
      }
  // An already requested cooperative stop must not masquerade as UNSAT.
  // Stop checks may race with a trivial proof, so use a fresh nontrivial solve
  // and assert the observed pinned-backend result, then resume the same owner.
  {
    CaDiCaL::Solver solver; solver.set("quiet", 1);
    Cardinality external(solver, 8, 3, 0, false);
    Stop stop; solver.connect_terminator(&stop);
    const int first = solver.solve(); assert(first == 0 && stop.calls);
    stop.stopped = false;
    assert(solver.solve() == 10);
    unsigned resumed = 0;
    for (int i = 1; i <= 8; ++i) if (solver.val(i) > 0) resumed |= 1u << (i - 1);
    assert(external.satisfied(resumed));
    solver.disconnect_terminator(); total += external.counts;
  }
  assert(total.propagations && total.reason_streams && total.external_clauses);
  assert(total.rejected_models && total.backtracks && total.nonchronological_backtracks);
  assert(total.delayed_reasons && total.checked_lemmas);
  std::cout << "{\"schema_version\":1,\"experiment\":\"cadical-ipasir-up\","
    << "\"queries\":" << queries << ",\"sat\":" << sat << ",\"unsat\":" << unsat
    << ",\"assignments\":" << total.assignments << ",\"decisions\":" << total.decisions
    << ",\"backtracks\":" << total.backtracks
    << ",\"nonchronological_backtracks\":" << total.nonchronological_backtracks
    << ",\"propagations\":" << total.propagations << ",\"reason_streams\":" << total.reason_streams
    << ",\"delayed_reasons\":" << total.delayed_reasons
    << ",\"external_clauses\":" << total.external_clauses
    << ",\"checked_models\":" << total.checked_models
    << ",\"rejected_models\":" << total.rejected_models
    << ",\"checked_lemmas\":" << total.checked_lemmas << ",\"status\":\"passed\"}\n";
}

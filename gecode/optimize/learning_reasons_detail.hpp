/* Private pilot: checked conditional reasons for original integer linear rows.
 * No existing propagator, search, SAT interface, or public solve API uses this.
 */
#ifndef GECODE_OPTIMIZE_LEARNING_REASONS_DETAIL_HPP
#define GECODE_OPTIMIZE_LEARNING_REASONS_DETAIL_HPP
#include <gecode/optimize/model.hpp>
#include <gecode/optimize/result.hpp>
#include <memory>
#include <variant>

namespace Gecode { namespace Optimize { namespace Detail { namespace Learning {
struct KernelAccess;
struct CompiledData;

enum class Side { Lower, Upper };
struct BoundFact {
  Variable variable;
  Side side=Side::Lower;
  std::int64_t value=0;
};
struct Contradiction {};
using Conclusion=std::variant<BoundFact,Contradiction>;

/** Exact owned source, never authenticated by model/revision tags alone. */
class Source final {
public:
  ~Source();
  Source(const Source&)=delete;
  Source& operator=(const Source&)=delete;
  ModelId id() const noexcept {return original_.model_id;}
  Revision revision() const noexcept {return original_.revision;}
  const ModelSnapshot& original() const noexcept {return original_;}
private:
  friend struct KernelAccess;
  Source(ModelSnapshot,std::unique_ptr<const CompiledData>);
  ModelSnapshot original_;
  std::unique_ptr<const CompiledData> compiled_;
};

/** Untrusted conditional claim. All facts are antecedents, not global truths.
 * Facts are strictly ordered by (variable slot, Lower then Upper), with at most
 * one per slot/side, and must strengthen the named original domain side.
 * Facts and a bound conclusion refer to live variables occurring in this row.
 */
struct Candidate {
  std::shared_ptr<const Source> source;
  ModelId model_id=0;
  Revision revision=0;
  Constraint row;
  Side row_side=Side::Lower;
  std::vector<BoundFact> antecedents;
  Conclusion conclusion;
};

/** Only a completed checker can construct this immutable owning record. */
class VerifiedReason final {
public:
  VerifiedReason(const VerifiedReason&)=delete;
  VerifiedReason& operator=(const VerifiedReason&)=delete;
  const Candidate& claim() const noexcept {return candidate_;}
private:
  friend struct KernelAccess;
  explicit VerifiedReason(Candidate);
  Candidate candidate_;
};

struct Limits {
  /** Original slots include tombstones; nonzeros include active rows only. */
  std::size_t max_variable_slots=100000,max_row_slots=100000,max_nonzeros=1000000;
  std::size_t max_facts=100000,max_reasons=200000;
  /** Conservative logical slots and element visits, not bytes or CPU time. */
  std::size_t max_retained_slots=8000000,max_work=100000000;
};
struct Options {
  double time_limit_seconds=std::numeric_limits<double>::infinity();
  std::shared_ptr<CancellationToken> cancellation;
  Limits limits;
};
enum class State {
  Complete,Unsupported,InvalidInput,ArithmeticOverflow,ResourceLimit,
  Stopped,AllocationFailure,InternalError
};
struct Work {
  std::size_t coordinator_visits=0,retained_slots=0,reasons_checked=0;
};
struct Report {
  State state=State::InvalidInput;
  ModelId model_id=0;
  Revision revision=0;
  std::optional<Termination> stop_reason;
  std::string message;
  Work work;
  double elapsed_seconds=0;
};
struct SourceResult : Report {std::shared_ptr<const Source> source;};
struct CheckResult : Report {std::shared_ptr<const VerifiedReason> reason;};
struct BatchResult : Report {std::vector<std::shared_ptr<const VerifiedReason>> reasons;};

/** Copy/admission occurs inside this measured call. Only finite integral
 * Integer/Binary domains and ordinary rows with integral data within +/-2^53
 * are admitted. Infinite absent row sides are allowed. Objective is structurally
 * validated but has no role in this feasibility-reason utility.
 */
SourceResult compile_source(const ModelSnapshot&,const Options& = {});

/** Uses expected_source pointer identity AND tags, then independently reads
 * original domains/row data. Antecedents must be consistent before negating a
 * strict non-root/non-redundant bound conclusion. Complement/row arithmetic is
 * checked int64; overflow is rejection, never an accepted vacuous implication.
 * A constant-row contradiction with zero antecedents is a valid explicit claim.
 */
CheckResult check_reason(const std::shared_ptr<const Source>& expected_source,
                         const Candidate&,const Options& = {});

/** One unchanged box reconstructed from original domains and explicit facts.
 * Both finite sides are considered. First pilot retains every row-specific
 * input fact in each reason; it does not minimize explanations. Generation and
 * every independent verification share one meter. Only a complete verified
 * batch is returned; an empty Complete batch means no deduction, not conflict.
 */
BatchResult generate_row_reasons(const std::shared_ptr<const Source>&,Constraint,
                                 const std::vector<BoundFact>&,
                                 const Options& = {});
}}}}
#endif

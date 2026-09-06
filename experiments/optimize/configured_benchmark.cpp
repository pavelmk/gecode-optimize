/* Explicit algorithm benchmark driver; frozen inputs provide no solver start. */
#include <gecode/optimize/native.hpp>
#include <gecode/optimize/native_neighborhoods.hpp>
#include <gecode/optimize/globals.hpp>

#include <algorithm>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace O = Gecode::Optimize;
using Clock = std::chrono::steady_clock;

namespace {
struct Reader {
  std::ifstream file;
  explicit Reader(const std::string& path) : file(path) {
    if (!file) throw std::runtime_error("Cannot open frozen TXT input");
    file.seekg(0, std::ios::end);
    const auto bytes = file.tellg();
    if (bytes < 0 || bytes > 4*1024*1024)
      throw std::runtime_error("TXT input size limit");
    file.seekg(0);
  }
  std::string token() {
    std::string value;
    if (!(file >> value) || value.size() > 100)
      throw std::runtime_error("Missing/oversized TXT token");
    return value;
  }
  std::int64_t integer(std::int64_t lower, std::int64_t upper) {
    const auto text = token();
    std::int64_t value = 0;
    const auto parsed = std::from_chars(text.data(), text.data()+text.size(), value);
    if (parsed.ec != std::errc() || parsed.ptr != text.data()+text.size() ||
        value < lower || value > upper)
      throw std::runtime_error("Invalid/out-of-range TXT integer");
    return value;
  }
  void end() {
    std::string extra;
    if (file >> extra) throw std::runtime_error("Trailing TXT content");
    if (!file.eof()) throw std::runtime_error("TXT read failure");
  }
};

struct Built {
  O::Model model;
  std::vector<O::Variable> original;
};

Built binary(Reader& input) {
  Built out;
  const auto n = static_cast<std::size_t>(input.integer(1, 10000));
  const auto m = static_cast<std::size_t>(input.integer(0, 100000));
  out.original = out.model.add_variables(
    std::vector<O::VariableSpec>(n, {O::VariableType::Binary, 0, 1, {}}));
  std::vector<O::Term> objective;
  for (std::size_t j=0; j<n; ++j) {
    const auto cost = input.integer(-1000000000, 1000000000);
    if (cost) objective.push_back({out.original[j], static_cast<double>(cost)});
  }
  O::SparseRowBatch rows;
  rows.columns = out.original;
  std::size_t total = 0;
  for (std::size_t i=0; i<m; ++i) {
    rows.lower.push_back(static_cast<double>(input.integer(-1000000000,1000000000)));
    rows.upper.push_back(std::numeric_limits<double>::infinity());
    const auto count = static_cast<std::size_t>(input.integer(0, static_cast<std::int64_t>(n)));
    if (count > 2000000-total) throw std::runtime_error("TXT nonzero limit");
    total += count;
    std::int64_t previous = -1;
    for (std::size_t k=0; k<count; ++k) {
      const auto column = input.integer(0, static_cast<std::int64_t>(n)-1);
      const auto coefficient = input.integer(-1000000000, 1000000000);
      if (column <= previous || !coefficient)
        throw std::runtime_error("Noncanonical TXT row");
      previous = column;
      rows.column.push_back(static_cast<std::size_t>(column));
      rows.coefficient.push_back(static_cast<double>(coefficient));
    }
    rows.row_start.push_back(rows.column.size());
  }
  out.model.add_rows_sparse(rows);
  out.model.minimize(objective);
  if (input.token() != "incumbent")
    throw std::runtime_error("Missing legacy incumbent marker");
  const auto present = input.integer(0, 1);
  // Legacy files contain a reference-free initial witness. Parse and discard it;
  // neither this witness nor any reference objective enters solve options.
  if (present)
    for (std::size_t i=0; i<n; ++i) (void)input.integer(0, 1);
  input.end();
  return out;
}

Built global(Reader& input, const std::string& expected) {
  if (input.token() != expected)
    throw std::runtime_error("Native TXT family differs from requested kind");
  const auto n = static_cast<std::size_t>(input.integer(1, 100));
  if (input.integer(0, 0) != 0 || input.integer(1, 100) != static_cast<std::int64_t>(n))
    throw std::runtime_error("Native TXT dimensions");
  std::vector<std::int64_t> costs(n*n);
  for (auto& cost : costs) cost = input.integer(0, 100000);
  for (std::size_t j=0; j<n; ++j) (void)input.integer(0, static_cast<std::int64_t>(n)-1);
  input.end();
  Built out;
  for (std::size_t j=0; j<n; ++j)
    out.original.push_back(out.model.add_integer(0, static_cast<double>(n)-1));
  if (expected == "native_tsp") O::add_circuit(out.model, out.original);
  else {
    O::add_all_different(out.model,out.original);
    std::vector<O::Variable> rising, falling;
    for (std::size_t j=0; j<n; ++j) {
      const auto a=out.model.add_integer(static_cast<double>(j),static_cast<double>(n+j-1));
      const auto b=out.model.add_integer(-static_cast<double>(j),static_cast<double>(n-1)-j);
      out.model.add_row({{a,1},{out.original[j],-1}},static_cast<double>(j),static_cast<double>(j));
      out.model.add_row({{b,1},{out.original[j],-1}},-static_cast<double>(j),-static_cast<double>(j));
      rising.push_back(a);
      falling.push_back(b);
    }
    O::add_all_different(out.model, rising);
    O::add_all_different(out.model, falling);
  }
  std::vector<O::Term> objective;
  for (std::size_t j=0; j<n; ++j) {
    const auto begin = costs.begin()+j*n, end = begin+n;
    const auto cost=out.model.add_integer(static_cast<double>(*std::min_element(begin,end)),
                                         static_cast<double>(*std::max_element(begin,end)));
    std::vector<std::vector<std::int64_t>> tuples;
    for (std::size_t k=0; k<n; ++k)
      tuples.push_back({static_cast<std::int64_t>(k), costs[j*n+k]});
    O::add_table(out.model, {out.original[j], cost}, tuples);
    objective.push_back({cost, 1});
  }
  out.model.minimize(objective);
  return out;
}

std::string quote(const std::string& text) {
  std::ostringstream out;
  out << '"';
  for (unsigned char c : text) {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c < 32)
      out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << unsigned(c) << std::dec;
    else out << c;
  }
  out << '"';
  return out.str();
}

void optional(const std::optional<double>& value) {
  if (!value) std::cout << "null";
  else if (!std::isfinite(*value)) throw std::runtime_error("Nonfinite original result scalar");
  else std::cout << *value;
}

const char* completion(O::NativeRootCoverCompletion value) {
#define COVER_CASE(name) case O::NativeRootCoverCompletion::name: return #name
  switch (value) {
    COVER_CASE(NotRequested); COVER_CASE(NotStarted); COVER_CASE(NoNewCuts);
    COVER_CASE(RoundLimit); COVER_CASE(WorkLimit); COVER_CASE(StorageLimit);
    COVER_CASE(SeparationLimit); COVER_CASE(Cancelled); COVER_CASE(TimeLimit);
    COVER_CASE(NoPrimalSuggestion); COVER_CASE(InvalidSuggestion);
    COVER_CASE(CallbackError); COVER_CASE(BackendError); COVER_CASE(AllocationFailure);
  }
#undef COVER_CASE
  throw std::runtime_error("Unknown root-cover completion");
}

const char* completion(O::NativeNeighborhoodCompletion value) {
#define NEIGHBOR_CASE(name) case O::NativeNeighborhoodCompletion::name: return #name
  switch (value) {
    NEIGHBOR_CASE(NotStarted); NEIGHBOR_CASE(NoIncumbent);
    NEIGHBOR_CASE(ProofCompletedBeforeAttempt); NEIGHBOR_CASE(NoEligibleBinary);
    NEIGHBOR_CASE(NonrestrictingRadius); NEIGHBOR_CASE(FormulationLimit);
    NEIGHBOR_CASE(SourceLimit); NEIGHBOR_CASE(WorkLimit); NEIGHBOR_CASE(StatusLimit);
    NEIGHBOR_CASE(SharedNodeReserve); NEIGHBOR_CASE(LocalStorageLimit);
    NEIGHBOR_CASE(LocalTimeLimit); NEIGHBOR_CASE(NoImprovement);
    NEIGHBOR_CASE(Improved); NEIGHBOR_CASE(GlobalStop); NEIGHBOR_CASE(Error);
  }
#undef NEIGHBOR_CASE
  throw std::runtime_error("Unknown neighborhood completion");
}

struct Configuration {
  bool frontier = false, checked_lp = false, covers = false;
  bool reliability = false, neighborhoods = false;
  O::NativeLpSettings lp;
  O::NativeBranchingSettings branching;
  O::NativeNeighborhoodSettings neighborhood;
  std::size_t max_open_nodes = 1024;

  explicit Configuration(const std::string& route) {
    if (route == "native") return;
    if (route == "lp-root") checked_lp = true;
    else if (route == "lp-cuts") checked_lp = covers = true;
    else if (route == "lp-updated") {
      checked_lp = covers = true;
      lp.frequency = O::NativeLpFrequency::AfterBoundChanges;
    } else if (route == "dfs-reliability") frontier = reliability = true;
    else if (route == "lp-reliability" || route == "lp-reliability-neighborhood") {
      frontier = reliability = checked_lp = covers = true;
      lp.frequency = O::NativeLpFrequency::AfterBoundChanges;
      neighborhoods = route == "lp-reliability-neighborhood";
    } else throw std::runtime_error("Invalid driver route");
    if (lp.frequency == O::NativeLpFrequency::AfterBoundChanges)
      lp.bound_change_interval = 4;
    if (covers) lp.root_cover_cuts = O::NativeRootCoverSettings{};
    neighborhood.radius = 4;
    neighborhood.time_limit_seconds = 0.05;
  }

  void print() const {
    const auto flag = [](bool value) { return value ? "true" : "false"; };
    std::cout << "{\"entry_point\":" << quote(neighborhoods ? "solve_native_neighborhoods" :
        frontier ? "solve_native_search" : checked_lp ? "solve_native_lp" : "solve_native")
      << ",\"search_order\":" << quote(frontier ? "depth_first" : "native_bab")
      << ",\"checked_lp\":" << flag(checked_lp)
      << ",\"lp_frequency\":";
    if (checked_lp) std::cout << quote(lp.frequency == O::NativeLpFrequency::Root ? "root" : "after_bound_changes");
    else std::cout << "null";
    std::cout << ",\"bound_tightening\":" << flag(checked_lp && lp.bound_tightening)
      << ",\"bound_change_interval\":";
    if (checked_lp) std::cout << lp.bound_change_interval; else std::cout << "null";
    std::cout << ",\"root_cover_cuts\":" << flag(covers)
      << ",\"binary_reliability\":" << flag(reliability)
      << ",\"neighborhoods\":" << flag(neighborhoods)
      // Eligibility of this route is not a claim that the model passes the
      // internal DP admission checks. The public API has no DP-used counter.
      << ",\"knapsack_dp_eligible_route\":" << flag(!checked_lp)
      << ",\"presolve\":false,\"max_open_nodes\":";
    if (frontier) std::cout << max_open_nodes; else std::cout << "null";
    std::cout << ",\"cover_settings\":";
    if (covers) {
      const auto& c = *lp.root_cover_cuts;
#define CONFIG_FIELD(name) << ",\"" #name "\":" << c.name
      std::cout << "{\"max_rounds\":" << c.max_rounds
        CONFIG_FIELD(max_work) CONFIG_FIELD(max_cuts) CONFIG_FIELD(max_cut_nonzeros)
        CONFIG_FIELD(max_model_columns) CONFIG_FIELD(max_model_rows)
        CONFIG_FIELD(max_model_nonzeros) CONFIG_FIELD(max_separation_rows)
        CONFIG_FIELD(max_terms_per_row) CONFIG_FIELD(denominator) << '}';
#undef CONFIG_FIELD
    } else std::cout << "null";
    std::cout << ",\"branching_settings\":";
    if (reliability) {
      const auto& c = branching;
#define CONFIG_FIELD(name) << ",\"" #name "\":" << c.name
      std::cout << "{\"policy\":\"binary_reliability\""
        CONFIG_FIELD(max_candidates_per_decision) CONFIG_FIELD(max_probe_status_calls)
        CONFIG_FIELD(max_probe_status_calls_per_decision) CONFIG_FIELD(max_branching_work)
        CONFIG_FIELD(reliability_samples) CONFIG_FIELD(max_nonimproving_pairs)
        CONFIG_FIELD(max_history_entries) << '}';
#undef CONFIG_FIELD
    } else std::cout << "null";
    std::cout << ",\"neighborhood_settings\":";
    if (neighborhoods) {
      const auto& c = neighborhood;
#define CONFIG_FIELD(name) << ",\"" #name "\":" << c.name
      std::cout << "{\"policy\":\"binary_hamming\""
        CONFIG_FIELD(radius) CONFIG_FIELD(max_status_calls) CONFIG_FIELD(max_distance_variables)
        CONFIG_FIELD(max_source_entries) CONFIG_FIELD(max_coordinator_work)
        CONFIG_FIELD(max_local_spaces) CONFIG_FIELD(time_limit_seconds) << '}';
#undef CONFIG_FIELD
    } else std::cout << "null";
    std::cout << '}';
  }
};

void print_statistics(const O::NativeLpStatistics& lp,
                      const O::NativeBranchingStatistics& branching,
                      const O::NativeNeighborhoodStatistics& neighborhood) {
  std::cout << ",\"relaxation\":{\"lp_calls\":" << lp.lp_calls;
#define LP_FIELD(name) << ",\"" #name "\":" << lp.name
  std::cout LP_FIELD(lp_seconds) LP_FIELD(valid_bounds) LP_FIELD(rejected_bounds)
    LP_FIELD(numerical_infeasibility_reports) LP_FIELD(certificate_evaluations)
    LP_FIELD(conditional_checks) LP_FIELD(variable_fixings) LP_FIELD(variable_bound_tightenings);
#undef LP_FIELD
  const auto& c = lp.root_cover;
  std::cout << ",\"root_cover\":{\"requested\":" << (c.requested ? "true" : "false")
    << ",\"completion\":" << quote(completion(c.completion));
#define CUT_FIELD(name) << ",\"" #name "\":" << c.name
  std::cout CUT_FIELD(rounds) CUT_FIELD(augmentations) CUT_FIELD(cuts) CUT_FIELD(nonzeros)
    CUT_FIELD(work) CUT_FIELD(projected_coordinates) CUT_FIELD(unsupported_rows)
    CUT_FIELD(oversized_rows) CUT_FIELD(separated_cuts) CUT_FIELD(duplicate_cuts)
    CUT_FIELD(arithmetic_rejections) CUT_FIELD(lp_calls) CUT_FIELD(valid_bounds)
    CUT_FIELD(rejected_bounds) CUT_FIELD(numerical_infeasibility_reports)
    CUT_FIELD(lp_seconds) << "}}";
#undef CUT_FIELD
  const auto& b = branching;
  std::cout << ",\"branching\":{\"requested\":" << (b.requested ? "true" : "false");
#define BRANCH_FIELD(name) << ",\"" #name "\":" << b.name
  std::cout BRANCH_FIELD(decisions) BRANCH_FIELD(manual_splits) BRANCH_FIELD(fallback_decisions)
    BRANCH_FIELD(probe_status_calls) BRANCH_FIELD(completed_pairs) BRANCH_FIELD(published_pairs)
    BRANCH_FIELD(finite_samples) BRANCH_FIELD(zero_gain_samples) BRANCH_FIELD(failed_directions)
    BRANCH_FIELD(reliable_candidates) BRANCH_FIELD(probe_propagations) BRANCH_FIELD(budget_nodes)
    BRANCH_FIELD(work) BRANCH_FIELD(history_entries) BRANCH_FIELD(probe_lp_calls)
    BRANCH_FIELD(probe_lp_seconds) << '}';
#undef BRANCH_FIELD
  const auto& n = neighborhood;
  std::cout << ",\"neighborhood\":{\"requested\":" << (n.requested ? "true" : "false")
    << ",\"completion\":" << quote(completion(n.completion)) << ",\"stop_reason\":";
  if (n.stop_reason) std::cout << quote(O::to_string(*n.stop_reason)); else std::cout << "null";
#define NEIGHBOR_FIELD(name) << ",\"" #name "\":" << n.name
  std::cout NEIGHBOR_FIELD(attempts) NEIGHBOR_FIELD(eligible_variables)
    NEIGHBOR_FIELD(source_entries) NEIGHBOR_FIELD(coordinator_work)
    NEIGHBOR_FIELD(status_attempts) NEIGHBOR_FIELD(completed_status_calls)
    NEIGHBOR_FIELD(failed_nodes) NEIGHBOR_FIELD(feasible_candidates)
    NEIGHBOR_FIELD(accepted_improvements) NEIGHBOR_FIELD(peak_local_spaces)
    NEIGHBOR_FIELD(peak_total_spaces) NEIGHBOR_FIELD(budget_nodes)
    NEIGHBOR_FIELD(elapsed_seconds) << '}';
#undef NEIGHBOR_FIELD
}
}

int main(int argc, char** argv) {
  const auto start=Clock::now();
  const auto elapsed=[&] {return std::chrono::duration<double>(Clock::now()-start).count();};
  try {
    if (argc!=9 || std::string(argv[1])!="--input" || std::string(argv[3])!="--kind" ||
        std::string(argv[5])!="--route" || std::string(argv[7])!="--seconds")
      throw std::runtime_error("Usage: configured-benchmark --input TXT --kind binary|native_tsp|weighted_queens --route native|lp-root|lp-cuts|lp-updated|dfs-reliability|lp-reliability|lp-reliability-neighborhood --seconds N (0 < N <= 10)");
    const std::string kind=argv[4],route=argv[6],time_text=argv[8];std::size_t used=0;
    const double seconds=std::stod(time_text,&used);
    if (used!=time_text.size() || !std::isfinite(seconds) || seconds<=0 || seconds>10 ||
        (kind!="binary" && kind!="native_tsp" && kind!="weighted_queens"))
      throw std::runtime_error("Invalid driver kind, route or seconds");
    const Configuration configuration(route);
    Reader input(argv[2]);auto built=kind=="binary"?binary(input):global(input,kind);
    const auto snapshot=built.model.snapshot();const double build_seconds=elapsed();
    O::SolveOptions options;options.backend=O::Backend::Native;options.guarantee=O::Guarantee::Exact;
    options.time_limit_seconds=seconds;options.random_seed=0;options.threads=1;
    options.relative_gap=0;options.absolute_gap=0;
    O::SolveResult result;std::optional<O::NativeSearchResult> frontier;
    O::NativeLpStatistics relaxation;
    O::NativeNeighborhoodStatistics neighborhood;
    const auto solve_start=Clock::now();
    if (configuration.frontier) {
      O::NativeSearchOptions search;search.solve=options;search.order=O::NativeSearchOrder::DepthFirst;
      search.max_open_nodes=configuration.max_open_nodes;
      if (configuration.checked_lp) search.relaxation=configuration.lp;
      if (configuration.reliability) search.branching=configuration.branching;
      if (configuration.neighborhoods) {
        O::NativeNeighborhoodOptions local;
        local.search=search;local.neighborhood=configuration.neighborhood;
        auto solved=O::solve_native_neighborhoods(snapshot,local);
        neighborhood=solved.neighborhood;frontier=std::move(solved.search);
      } else frontier=O::solve_native_search(snapshot,search);
      result=frontier->result;relaxation=frontier->relaxation;
    } else if (configuration.checked_lp) {
      O::NativeLpOptions lp;
      static_cast<O::NativeLpSettings&>(lp)=configuration.lp;lp.solve=options;
      auto solved=O::solve_native_lp(snapshot,lp);
      result=std::move(solved.result);relaxation=solved.relaxation;
    } else result=O::solve_native(snapshot,options);
    const double solve_seconds=std::chrono::duration<double>(Clock::now()-solve_start).count();
    const bool point=result.has_solution();
    if (result.model_id!=snapshot.model_id || result.revision!=snapshot.revision)
      throw std::runtime_error("Result original identity mismatch");
    if (point && (result.values.size()!=snapshot.variables.size() || result.active_variables.size()!=snapshot.variables.size()))
      throw std::runtime_error("Result original slot dimensions");
    std::cout<<std::setprecision(17)<<"{\"schema_version\":1,\"kind\":"<<quote(kind)<<",\"route\":"<<quote(route)
      <<",\"status\":"<<quote(O::to_string(result.termination))<<",\"backend\":"<<quote(result.backend)
      <<",\"backend_version\":"<<quote(result.backend_version)<<",\"guarantee\":"<<quote(result.guarantee==O::Guarantee::Exact?"exact":"other")
      <<",\"message\":"<<quote(result.message)<<",\"solution_validated\":"<<(result.solution_validated?"true":"false")
      <<",\"has_solution\":"<<(point?"true":"false")<<",\"start_submitted\":"<<(result.start_submitted?"true":"false")
      <<",\"model_id\":"<<result.model_id<<",\"revision\":"<<result.revision
      <<",\"model_columns\":"<<snapshot.variables.size()<<",\"model_rows\":"<<snapshot.rows.size()
      <<",\"model_globals\":"<<snapshot.globals.size()<<",\"objective\":";optional(result.objective);
    std::cout<<",\"best_bound\":";optional(result.best_bound);
    std::cout<<",\"absolute_gap\":";optional(result.absolute_gap);
    std::cout<<",\"relative_gap\":";optional(result.relative_gap);
    std::cout<<",\"build_seconds\":"<<build_seconds<<",\"solve_seconds\":"<<solve_seconds
      <<",\"backend_solve_seconds\":"<<result.elapsed_seconds
      <<",\"driver_seconds\":"<<elapsed()<<",\"assignment\":[";
    if (point) for (std::size_t j=0;j<built.original.size();++j) {
      if (j) std::cout << ',';
      std::cout << result.value(built.original[j]);
    }
    std::cout<<"],\"full_values\":[";
    if (point) for (std::size_t j=0;j<result.values.size();++j) {
      if(!result.active_variables[j] || !std::isfinite(result.values[j]))throw std::runtime_error("Invalid active original value");
      if (j) std::cout << ',';
      std::cout << result.values[j];
    }
    std::cout<<"],\"nodes\":";
    if (frontier) std::cout<<frontier->frontier.admitted_nodes;else std::cout<<"null";
    std::cout<<",\"node_count_scope\":"<<quote(frontier?"frontier admitted status attempts":"unavailable in ordinary SolveResult")
      <<",\"expanded_nodes\":";
    if(frontier)std::cout<<frontier->frontier.expanded_nodes;else std::cout<<"null";
    std::cout<<",\"budget_nodes\":";
    if(frontier)std::cout<<frontier->branching.budget_nodes;else std::cout<<"null";
    std::cout<<",\"peak_open_nodes\":";
    if(frontier)std::cout<<frontier->frontier.peak_open_nodes;else std::cout<<"null";
    std::cout<<",\"unresolved_regions\":";
    if(frontier)std::cout<<frontier->frontier.unresolved_regions;else std::cout<<"null";
    std::cout<<",\"algorithm_configuration\":";configuration.print();
    print_statistics(relaxation,frontier?frontier->branching:O::NativeBranchingStatistics{},neighborhood);
    std::cout<<"}\n";return 0;
  } catch (const std::exception& error) {
    std::cerr<<"configured benchmark error: "<<error.what()<<'\n';return 2;
  }
}

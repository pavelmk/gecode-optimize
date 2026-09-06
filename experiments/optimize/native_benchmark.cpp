/* Fixed-input native algorithm comparison driver; no reference or start is used. */
#include <gecode/optimize/native.hpp>
#include <gecode/optimize/native_search.hpp>
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
}

int main(int argc, char** argv) {
  const auto start=Clock::now();
  const auto elapsed=[&] {return std::chrono::duration<double>(Clock::now()-start).count();};
  try {
    if (argc!=9 || std::string(argv[1])!="--input" || std::string(argv[3])!="--kind" ||
        std::string(argv[5])!="--route" || std::string(argv[7])!="--seconds")
      throw std::runtime_error("Usage: native-benchmark --input TXT --kind binary|native_tsp|weighted_queens --route native|dfs --seconds N");
    const std::string kind=argv[4],route=argv[6],time_text=argv[8];std::size_t used=0;
    const double seconds=std::stod(time_text,&used);
    if (used!=time_text.size() || !std::isfinite(seconds) || seconds<=0 || seconds>10 ||
        (kind!="binary" && kind!="native_tsp" && kind!="weighted_queens") || (route!="native"&&route!="dfs"))
      throw std::runtime_error("Invalid driver kind, route or seconds");
    Reader input(argv[2]);auto built=kind=="binary"?binary(input):global(input,kind);
    const auto snapshot=built.model.snapshot();const double build_seconds=elapsed();
    O::SolveOptions options;options.backend=O::Backend::Native;options.guarantee=O::Guarantee::Exact;
    options.time_limit_seconds=seconds;options.random_seed=0;options.threads=1;
    options.relative_gap=0;options.absolute_gap=0;
    O::SolveResult result;std::optional<O::NativeSearchResult> frontier;
    if (route=="native") result=O::solve_native(snapshot,options);
    else {
      O::NativeSearchOptions search;search.solve=options;search.order=O::NativeSearchOrder::DepthFirst;
      search.max_open_nodes=1024;frontier=O::solve_native_search(snapshot,search);result=frontier->result;
    }
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
    std::cout<<",\"build_seconds\":"<<build_seconds<<",\"solve_seconds\":"<<result.elapsed_seconds
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
    std::cout<<"}\n";return 0;
  } catch (const std::exception& error) {
    std::cerr<<"native benchmark error: "<<error.what()<<'\n';return 2;
  }
}

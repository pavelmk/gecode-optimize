/* Explicit, bounded FlatZinc capture/compiler frontend. Legacy driver is separate. */
#include <gecode/flatzinc/capture.hh>
#include <gecode/optimize/flatzinc.hpp>
#include <gecode/optimize/solve.hpp>
#include <gecode/optimize/validate.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <locale>
#include <set>
#include <sstream>
#include <stdexcept>

namespace FznOptimizeDriver {
namespace O=Gecode::Optimize;
namespace F=Gecode::FlatZinc::Capture;
using Clock=std::chrono::steady_clock;
struct Options {
  std::string filename;
  bool minizinc=false;
  F::Options capture;
  O::SolveOptions solve;
  Options() {
    solve.backend=O::Backend::Native;solve.guarantee=O::Guarantee::Exact;
    solve.relative_gap=0;solve.absolute_gap=0;
  }
};
const char* usage() {
  return "Usage: fzn-gecode-optimize MODEL.fzn|- [--backend native|highs] "
    "[--time-limit SECONDS] [--node-limit N] [--max-input-bytes N]\n"
    "One satisfaction solution or final optimization; bounded integer/Boolean subset.\n"
    "Native uses exact integer search; HiGHS is explicitly numerical.\n"
    "MiniZinc protocol: --minizinc [-t MILLISECONDS] MODEL.fzn|-\n";
}
std::uint64_t count(const std::string& text) {
  if(text.empty())throw std::invalid_argument("Empty count");
  std::uint64_t value=0;
  for(unsigned char c:text) {
    if(c<'0'||c>'9'||value>(std::numeric_limits<std::uint64_t>::max()-(c-'0'))/10)
      throw std::invalid_argument("Count must be an unsigned decimal integer in range");
    value=value*10+(c-'0');
  }
  return value;
}
double seconds(const std::string& text) {
  std::istringstream input(text);input.imbue(std::locale::classic());double value;
  input>>std::noskipws>>value;
  if(input.fail()||!input.eof()||!std::isfinite(value)||value<0)
    throw std::invalid_argument("Time limit must be finite and nonnegative");
  return value;
}
Options arguments(const std::vector<std::string>& args) {
  if(!args.empty()&&args[0]=="--minizinc") {
    Options options;options.minizinc=true;bool timed=false,filename_only=false;
    for(std::size_t i=1;i<args.size();++i) {
      const auto& arg=args[i];
      if(!filename_only&&arg=="--") {filename_only=true;continue;}
      if(!filename_only&&arg=="-t") {
        if(timed||i+1==args.size())throw std::invalid_argument("Missing or repeated -t time limit");
        timed=true;const auto milliseconds=count(args[++i]);
        // MiniZinc 2.10.1 treats a zero solver time limit as unlimited.
        if(milliseconds)options.solve.time_limit_seconds=static_cast<double>(milliseconds)/1000.0;
      } else if(arg.empty()||(!filename_only&&arg[0]=='-'&&arg!="-"))
        throw std::invalid_argument("Unsupported MiniZinc protocol option: "+arg);
      else {
        if(!options.filename.empty())throw std::invalid_argument("MiniZinc protocol requires exactly one model");
        options.filename=arg;
      }
    }
    if(options.filename.empty())throw std::invalid_argument("MiniZinc protocol requires exactly one model");
    options.capture.source=options.filename;options.solve.validate();return options;
  }
  if(args.empty()||args[0].empty()||(args[0][0]=='-'&&args[0]!="-"))
    throw std::invalid_argument(usage());
  Options options;options.filename=args[0];options.capture.source=args[0];std::set<std::string> seen;
  for(std::size_t i=1;i<args.size();i+=2) {
    const auto& key=args[i];
    if(i+1==args.size()||!seen.insert(key).second)throw std::invalid_argument("Missing or repeated option: "+key);
    const auto& value=args[i+1];
    if(key=="--backend") {
      if(value=="native") {options.solve.backend=O::Backend::Native;options.solve.guarantee=O::Guarantee::Exact;}
      else if(value=="highs") {options.solve.backend=O::Backend::Highs;options.solve.guarantee=O::Guarantee::Numerical;}
      else throw std::invalid_argument("Backend must be native or highs");
    } else if(key=="--time-limit")options.solve.time_limit_seconds=seconds(value);
    else if(key=="--node-limit")options.solve.node_limit=count(value);
    else if(key=="--max-input-bytes") {
      const auto n=count(value);
      if(n>static_cast<std::uint64_t>(std::numeric_limits<int>::max()))throw std::invalid_argument("Input limit exceeds parser index range");
      options.capture.max_input_bytes=static_cast<std::size_t>(n);
    } else throw std::invalid_argument("Unsupported option: "+key);
  }
  options.solve.validate();return options;
}
#ifdef GECODE_FLATZINC_DRIVER_TEST
O::SolveResult test_solve(const O::ModelSnapshot&,const O::SolveOptions&);
#endif
std::string location(const F::Location& at) {
  return at.source+(at.line?":"+std::to_string(at.line):"");
}
struct Output {std::string text;int code=1;};
Output render(const O::CompiledFlatZinc& compiled,const O::SolveResult& result,const Options& options) {
  switch(result.termination) {
    case O::Termination::Unsupported:case O::Termination::InvalidModel:
    case O::Termination::BackendError:case O::Termination::NumericalFailure:
      throw std::runtime_error(std::string(O::to_string(result.termination))+": "+result.message);
    default:break;
  }
  if(result.model_id!=compiled.model().model_id||result.revision!=compiled.model().revision)
    throw std::runtime_error("Backend returned a result for a different model");
  if(result.guarantee!=options.solve.guarantee)throw std::runtime_error("Backend returned a different guarantee");
  if(result.objective&&!std::isfinite(*result.objective))throw std::runtime_error("Backend returned a nonfinite objective");
  if(result.termination==O::Termination::Infeasible&&result.values.size()==compiled.model().variables.size()) {
    auto candidate=result;bool complete=true;
    candidate.active_variables.clear();
    for(const auto& v:compiled.model().variables) {
      candidate.active_variables.push_back(v.active);
      if(!v.active)continue;
      auto& x=candidate.values[v.variable.id];const auto rounded=std::round(x);
      if(!std::isfinite(x)||std::abs(x-rounded)>options.solve.integrality_tolerance) {complete=false;break;}
      x=rounded;
    }
    if(complete) {
      const auto checked=O::validate(compiled.model(),candidate.values,0,0);
      if(checked.valid&&checked.objective) {
        candidate.objective=checked.objective;candidate.solution_validated=true;
        if(O::validate_flatzinc(compiled,candidate,0).valid)
          throw std::runtime_error("Infeasible status contradicts the backend's original feasible assignment");
      }
    }
  }
  for(const auto& gap:{result.absolute_gap,result.relative_gap,result.native_backend_gap})
    if(gap&&(!std::isfinite(*gap)||*gap<0))throw std::runtime_error("Backend returned an invalid gap");
  if(result.best_bound&&!std::isfinite(*result.best_bound))throw std::runtime_error("Backend returned a nonfinite bound for the bounded model");
  if(result.objective&&result.best_bound) {
    auto checked=result;checked.update_gaps(compiled.model().objective.sense);
    if((result.absolute_gap&&result.absolute_gap!=checked.absolute_gap)||
       (result.relative_gap&&result.relative_gap!=checked.relative_gap))
      throw std::runtime_error("Backend returned inconsistent gap fields");
  } else if(result.absolute_gap||result.relative_gap)throw std::runtime_error("Backend returned gaps without an objective and bound");
  const bool point=result.has_solution();
  if((result.termination==O::Termination::Optimal&&!point)||
     (result.termination==O::Termination::Infeasible&&point))
    throw std::runtime_error("Backend returned inconsistent status and assignment");
  if(result.termination==O::Termination::Unbounded||result.termination==O::Termination::InfeasibleOrUnbounded)
    throw std::runtime_error("Unexpected unbounded status for the finite discrete model");
  // Do not silently hide a malformed claimed incumbent behind UNKNOWN or UNSAT.
  if(result.solution_validated&&!point)throw std::runtime_error("Backend returned a malformed incumbent");
  if(result.termination==O::Termination::Optimal&&compiled.source().solve.method!=F::Method::Satisfy) {
    if(!result.best_bound)throw std::runtime_error("Completed optimization has no bound");
    if(options.solve.guarantee==O::Guarantee::Exact&&result.best_bound!=result.objective)
      throw std::runtime_error("Exact optimal status has an open objective gap");
  }
  Output output;
  output.text=options.solve.backend==O::Backend::Native ? "% guarantee: exact integer search\n" : "% guarantee: numerical; requested MIP gaps: 0\n";
  if(point) {
    output.text+=O::format_flatzinc_solution(compiled,result,options.solve.integrality_tolerance);
    if(result.termination==O::Termination::Optimal) {
      if(compiled.source().solve.method!=F::Method::Satisfy)output.text+="==========\n";
      output.code=0;
    }
  } else if(result.termination==O::Termination::Infeasible) {
    output.text+="=====UNSATISFIABLE=====\n";output.code=0;
  } else output.text+="=====UNKNOWN=====\n";
  return output;
}
int execute(const Options& options,std::istream& input,std::ostream& out,std::ostream& errors) {
  const auto begin=Clock::now();
  const auto remaining=[&] {return std::max(0.0,options.solve.time_limit_seconds-
    std::chrono::duration<double>(Clock::now()-begin).count());};
  const auto expired=[&] {return remaining()==0;};
  const auto unknown=[&] {out<<"% time limit reached\n=====UNKNOWN=====\n";return options.minizinc?0:1;};
  try {
    if(expired())return unknown();
    auto captured=F::parse(input,options.capture);
    if(expired())return unknown();
    if(captured.status!=F::Status::Complete||!captured.records) {
      std::string message="FlatZinc capture failed";
      if(!captured.diagnostics.empty())message=location(captured.diagnostics[0].location)+": "+captured.diagnostics[0].message;
      throw std::runtime_error(message);
    }
    O::FlatZincCompileOptions compiler;compiler.time_limit_seconds=remaining();
    auto compiled=O::compile_flatzinc(*captured.records,compiler);
    if(expired()||compiled.status==O::FlatZincCompileStatus::TimeLimit)return unknown();
    if(compiled.status!=O::FlatZincCompileStatus::Complete||!compiled.compiled)
      throw std::runtime_error(location(compiled.location)+": "+compiled.message);
    auto solve_options=options.solve;solve_options.time_limit_seconds=remaining();
#ifdef GECODE_FLATZINC_DRIVER_TEST
    auto result=test_solve(compiled.compiled->model(),solve_options);
#else
    auto result=O::solve(compiled.compiled->model(),solve_options);
#endif
    // The parser has cooperative stage boundaries, not token-level interruption.
    // Never publish a newly returned point after the overall frontend deadline.
    if(expired())return unknown();
    auto output=render(*compiled.compiled,result,options);
    if(expired())return unknown();
    out<<output.text;
    if(output.code)errors<<"Solve stopped: "<<O::to_string(result.termination)<<"; "<<result.message<<'\n';
    return options.minizinc&&output.code==1?0:output.code;
  } catch(const std::bad_alloc&) {errors<<"FlatZinc optimization: memory allocation failed\n";return 2;}
    catch(const std::exception& e) {errors<<"FlatZinc optimization: "<<e.what()<<'\n';return 2;}
}
}
#ifndef GECODE_FLATZINC_DRIVER_TEST
int main(int argc,char** argv) {
  using namespace FznOptimizeDriver;
  if(argc==2&&std::string(argv[1])=="--help") {std::cout<<usage();return 0;}
  try {
    const auto options=arguments(std::vector<std::string>(argv+1,argv+argc));
    if(options.filename=="-")return execute(options,std::cin,std::cout,std::cerr);
    std::ifstream input(options.filename,std::ios::binary);
    if(!input)throw std::runtime_error("Cannot open input: "+options.filename);
    return execute(options,input,std::cout,std::cerr);
  } catch(const std::exception& e) {std::cerr<<"FlatZinc optimization: "<<e.what()<<'\n';return 2;}
}
#endif

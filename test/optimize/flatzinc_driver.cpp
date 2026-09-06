#define GECODE_FLATZINC_DRIVER_TEST 1
#include "../../tools/flatzinc/fzn-gecode-optimize.cpp"
#include <cassert>
#include <limits>

namespace FznOptimizeDriver {
int fake=0,calls=0;
O::SolveResult test_solve(const O::ModelSnapshot& m,const O::SolveOptions& options) {
  ++calls;if(!fake)return O::solve(m,options);
  O::SolveResult r;r.model_id=m.model_id;r.revision=m.revision;r.guarantee=options.guarantee;
  r.termination=O::Termination::Optimal;r.values.resize(m.variables.size(),0);
  r.active_variables.resize(m.variables.size(),true);r.solution_validated=true;r.objective=0;
  r.best_bound=0;r.absolute_gap=0;r.relative_gap=0;
  const auto clear=[&] {r.values.clear();r.active_variables.clear();r.objective.reset();r.best_bound.reset();r.absolute_gap.reset();r.relative_gap.reset();r.solution_validated=false;};
  switch(fake) {
    case 2:r.termination=O::Termination::NodeLimit;break;
    case 3:r.termination=O::Termination::NodeLimit;clear();break;
    case 4:r.values[0]=3;break;
    case 5:++r.model_id;break;
    case 6:r.active_variables[0]=false;break;
    case 7:clear();break;
    case 8:r.termination=O::Termination::Infeasible;break;
    case 9:r.termination=O::Termination::Infeasible;clear();break;
    case 10:r.guarantee=O::Guarantee::Certified;break;
    case 11:r.termination=O::Termination::BackendError;break;
    case 12:r.termination=O::Termination::Unsupported;break;
    case 13:r.objective=std::numeric_limits<double>::quiet_NaN();break;
    case 14:r.termination=O::Termination::Unbounded;clear();break;
    case 15:r.termination=O::Termination::Infeasible;r.solution_validated=false;r.objective.reset();r.best_bound.reset();r.absolute_gap.reset();r.relative_gap.reset();break;
    case 16:r.best_bound=1;break;
    case 17:r.best_bound=std::numeric_limits<double>::quiet_NaN();break;
    case 18:r.best_bound.reset();r.absolute_gap.reset();r.relative_gap.reset();break;
    case 19:r.best_bound=-1;r.absolute_gap=1;r.relative_gap=1;break;
    case 20:r.absolute_gap=std::numeric_limits<double>::quiet_NaN();break;
    case 21:r.relative_gap=1;break;
    case 22:r.termination=O::Termination::Infeasible;clear();r.objective=std::numeric_limits<double>::quiet_NaN();break;
    default:break;
  }
  return r;
}
}
using namespace FznOptimizeDriver;
namespace {
int checks=0;
const std::string basic="var 0..2: x :: output_var; solve minimize x;";
std::pair<int,std::string> run(const std::string& source,Options options={}) {
  std::istringstream input(source);std::ostringstream out,err;
  const int code=execute(options,input,out,err);++checks;
  if(code==2) {assert(out.str().empty());assert(!err.str().empty());}
  return {code,out.str()};
}
void rejected_arguments() {
  for(const auto& args:std::vector<std::vector<std::string>>{
    {},{"-a"},{"m","-a","1"},{"m","--backend","auto"},{"m","--backend"},
    {"m","--node-limit","-1"},{"m","--node-limit","1.5"},
    {"m","--node-limit","18446744073709551616"},{"m","--time-limit","nan"},
    {"m","--time-limit","-1"},{"m","--time-limit"," 2"},
    {"m","--time-limit","2x"},{"m","--max-input-bytes","2147483648"},
    {"m","--backend","native","--backend","highs"}}) {
    bool threw=false;try{arguments(args);}catch(const std::invalid_argument&){threw=true;}assert(threw);++checks;
  }
  auto valid=arguments({"-","--backend","highs","--time-limit","1e2","--node-limit","18446744073709551615"});
  assert(valid.solve.time_limit_seconds==100&&valid.solve.node_limit==std::numeric_limits<std::uint64_t>::max());++checks;
}
void fake_contract() {
  for(fake=1;fake<=22;++fake) {
    auto result=run(basic);
    if(fake==1)assert(result.first==0&&result.second.find("x = 0;\n----------\n==========\n")!=std::string::npos);
    else if(fake==2)assert(result.first==1&&result.second.find("x = 0;")!=std::string::npos&&result.second.find("==========")==std::string::npos);
    else if(fake==3)assert(result.first==1&&result.second.find("=====UNKNOWN=====")!=std::string::npos);
    else if(fake==9)assert(result.first==0&&result.second.find("=====UNSATISFIABLE=====")!=std::string::npos);
    else assert(result.first==2);
  }
  fake=1;auto sat=run("var 0..2: x :: output_var; solve satisfy;");
  assert(sat.first==0&&sat.second.find("x = 0;")!=std::string::npos&&sat.second.find("==========")==std::string::npos);
  calls=0;Options timed;timed.solve.time_limit_seconds=0;
  assert(run("not parsed",timed).first==1&&calls==0);
  Options small;small.capture.max_input_bytes=1;
  assert(run(basic,small).first==2&&calls==0);
  for(const auto& source:{
    "var 0..2: x; constraint mystery(x); solve satisfy;",
    "var 0..2: x; constraint int_times(x,x,x); solve satisfy;",
    "var int: x; solve minimize x;",
    "var 0.0..1.0: x; solve minimize x;",
    "var 0..2: x; solve :: int_search([x],input_order,indomain_min,complete) satisfy;",
    "var 0..2: x; constraint int_eq(x); solve satisfy;",
    "var 0..2: x; solve minimize missing;"})assert(run(source).first==2&&calls==0);
  // Finite holes are admitted now. A legal candidate reaches formatting, but
  // a forged value inside the hull and outside the set remains invalid.
  calls=0;
  auto holes=run("var {0,2}: x :: output_var; solve minimize x;");
  assert(holes.first==0&&calls==1&&holes.second.find("x = 0;")!=std::string::npos);
  calls=0;
  assert(run("var {-1,1}: x :: output_var; solve minimize x;").first==2&&calls==1);
  fake=0;
}
void actual_pipeline() {
  int available=0;
  for(auto backend:{O::Backend::Native,O::Backend::Highs}) {
    Options o;o.solve.backend=backend;o.solve.guarantee=backend==O::Backend::Native?O::Guarantee::Exact:O::Guarantee::Numerical;
    if(!O::capabilities(backend).available) {assert(run(basic,o).first==2);continue;}
    ++available;
    auto simple=run(basic,o);assert(simple.first==0&&simple.second.find("x = 0;")!=std::string::npos);
    auto maximum=run("var -2..3: x :: output_var; solve maximize x;",o);
    assert(maximum.first==0&&maximum.second.find("x = 3;")!=std::string::npos);
    auto aliases=run("var 0..3: x; var 1..2: y :: output_var = x; array [1..4] of var 0..3: a :: output_array([-1..0,2..3]) = [x,x,2,3]; solve minimize y;",o);
    assert(aliases.first==0&&aliases.second.find("a = array2d(-1..0, 2..3, [1, 1, 2, 3]);")!=std::string::npos&&aliases.second.find("y = 1;")!=std::string::npos);
    auto channel=run("var 0..1: x :: output_var; var bool: b :: output_var; constraint bool2int(b,x); constraint bool_eq(b,true); solve minimize x;",o);
    assert(channel.first==0&&channel.second.find("b = true;")!=std::string::npos&&channel.second.find("x = 1;")!=std::string::npos);
    auto unsat=run("var 0..1: x; constraint int_ge(x,2); solve satisfy;",o);
    assert(unsat.first==0&&unsat.second.find("=====UNSATISFIABLE=====")!=std::string::npos);
    auto hidden=run("var 0..2: hidden; var 0..2: x :: output_var; constraint int_plus(hidden,x,3); constraint int_eq(hidden,2); solve minimize x;",o);
    assert(hidden.first==0&&hidden.second.find("x = 1;")!=std::string::npos);
    for(const auto& source:{"int: p = 7; solve minimize p;","solve maximize -3;"}) {
      auto captured=F::parse_string(source);assert(captured.records);
      auto compiled=O::compile_flatzinc(*captured.records);assert(compiled.compiled);
      auto result=O::solve(compiled.compiled->model(),o.solve);
      assert(result.termination==O::Termination::Optimal&&result.objective==(std::string(source).find('7')!=std::string::npos?7:-3));
      assert(run(source,o).first==0);
    }
  }
#ifdef GECODE_FLATZINC_DRIVER_EXPECT_BACKEND
  assert(available>=1);
#else
  assert(available==0);
#endif
}
}
int main() {rejected_arguments();fake_contract();actual_pipeline();assert(checks>=50);std::cout<<"FlatZinc complete frontend: "<<checks<<" status/argument/source pipeline checks\n";}

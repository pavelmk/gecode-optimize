#ifdef NDEBUG
#undef NDEBUG
#endif
#include <gecode/optimize.hh>
#include <cassert>
#include <cmath>
#include <iostream>
#include <limits>
#include <optional>
using namespace Gecode::Optimize;
namespace {
constexpr double inf = std::numeric_limits<double>::infinity();
Model fixture(int kind) {
  Model m; std::vector<Variable> x; std::vector<Term> sum, cost;
  for (int i=0;i<10;++i) {
    x.push_back(m.add_binary()); sum.push_back({x.back(),kind>=3 ? double(i+1):1.0});
    cost.push_back({x.back(),double((i*7)%13+1)});
  }
  if (kind>=3) {
    if (kind==4) for (auto& t:sum) t.coefficient*=10000;
    m.add_row(sum,-inf,kind==4 ? 70000:17);m.maximize(cost);
  } else {
    m.add_row(sum,3,7);m.minimize(cost);
    if(kind==0) m.add_row({{x[0],1},{x[1],1}},1,inf);
    if(kind==1) for(int i=0;i<9;++i)m.add_row({{x[i],1},{x[i+1],-1}},-inf,0);
    if(kind==2)m.add_row({{x[0],3},{x[1],2},{x[3],4},{x[5],-2}},2,6);
  }
  return m;
}
// Independent exhaustive binary oracle, without solver or common validator.
std::pair<double,std::vector<double>> oracle(const ModelSnapshot& m) {
  double best=m.objective.sense==ObjectiveSense::Minimize ? inf:-inf;
  std::vector<double> witness;
  for(unsigned mask=0;mask<(1U<<m.variables.size());++mask){
    std::vector<double> point(m.variables.size());
    for(unsigned i=0;i<point.size();++i)point[i]=(mask>>i)&1U;
    bool valid=true;
    for(const auto& row:m.rows)if(row.active){
      double value=0;for(auto t:row.terms)value+=t.coefficient*point[t.variable.id];
      valid=valid && value>=row.lower && value<=row.upper;
    }
    if(!valid)continue;
    double value=m.objective.offset;
    for(auto t:m.objective.terms)value+=t.coefficient*point[t.variable.id];
    if(witness.empty() || (m.objective.sense==ObjectiveSense::Minimize ? value<best:value>best)){
      best=value;witness=point;
    }
  }
  return {best,witness};
}
void check(const ModelSnapshot& s,const SolveResult& r,double optimum){
  if(r.termination!=Termination::Optimal)std::cerr<<to_string(r.termination)<<": "<<r.message<<'\n';
  assert(r.termination==Termination::Optimal && r.solution_validated);
  assert(r.model_id==s.model_id && r.revision==s.revision);
  assert(r.objective==optimum && r.best_bound==r.objective);
  assert(r.message.find("Automatic native policy:")==0);
  double value=s.objective.offset;
  for(auto t:s.objective.terms)value+=t.coefficient*r.values[t.variable.id];
  assert(value==optimum);
  for(const auto& v:s.variables)assert(r.values[v.variable.id]==0 || r.values[v.variable.id]==1);
  for(const auto& row:s.rows){double a=0;for(auto t:row.terms)a+=t.coefficient*r.values[t.variable.id];assert(a>=row.lower && a<=row.upper);}
}
}
int main(){
  SolveOptions o;o.backend=Backend::Native;o.guarantee=Guarantee::Exact;
  o.relative_gap=o.absolute_gap=0;o.time_limit_seconds=5;
  if(!native_capabilities().available){
    auto m=fixture(0);
    assert(solve_native_auto(m,o).termination==Termination::Unsupported);
    assert(solve(m,o).termination==Termination::Unsupported);
    std::cout<<"Automatic native disabled-backend checks passed\n";return 0;
  }
  const bool lp=native_lp_capabilities().available;
  for(int kind=0;kind<5;++kind){
    auto m=fixture(kind);auto s=m.snapshot();auto expected=oracle(s);
    for(bool snapshot:{false,true}){
      auto r=snapshot ? solve(s,o):solve(m,o);check(s,r,expected.first);
      if(lp && kind!=3)assert(r.backend.find("checked LP")!=std::string::npos);
      else assert(r.backend==solve_native(s,o).backend);
      if(lp && (kind==2 || kind==4))assert(r.backend.find("frontier")!=std::string::npos);
    }
    auto started=o;for(unsigned i=0;i<s.variables.size();++i)started.primal_start.push_back({s.variables[i].variable,expected.second[i]});
    check(s,solve_native_auto(s,started),expected.first);
    auto defaults=o;defaults.relative_gap=1e-4;defaults.absolute_gap=1e-6;
    check(s,solve_native_auto(s,defaults),expected.first);
    auto stopped=o;stopped.time_limit_seconds=0;
    assert(solve_native_auto(s,stopped).termination==Termination::TimeLimit);
    stopped=o;stopped.cancellation=std::make_shared<CancellationToken>();stopped.cancellation->cancel();
    assert(solve_native_auto(s,stopped).termination==Termination::Cancelled);
    auto invalid=o;invalid.threads=0;
    assert(solve_native_auto(s,invalid).termination==Termination::InvalidModel);
    auto certified=o;certified.guarantee=Guarantee::Certified;
    assert(solve_native_auto(s,certified).termination==Termination::Unsupported);
    auto limited=o;limited.node_limit=1;auto r=solve_native_auto(s,limited);
    assert(r.termination==Termination::Optimal || r.termination==Termination::NodeLimit);
    if(r.best_bound)assert(s.objective.sense==ObjectiveSense::Minimize ? *r.best_bound<=expected.first:*r.best_bound>=expected.first);
    s.rows[0].terms[0].variable.id+=100;
    assert(solve_native_auto(s,o).termination==Termination::InvalidModel);
  }
  Model global;auto a=global.add_integer(0,2),b=global.add_integer(0,2);
  add_all_different(global,{a,b});global.minimize({{a,1},{b,1}});
  auto automatic=o;automatic.backend=Backend::Auto;auto g=solve(global,automatic);
  assert(g.termination==Termination::Optimal && g.objective==1 && g.backend=="Gecode native");
  Model large;for(int i=0;i<4100;++i)large.add_variable(VariableType::Binary,0,0);
  auto l=solve_native_auto(large,o);assert(l.termination==Termination::Optimal && l.objective==0);
  auto numeric=fixture(0);auto ns=numeric.snapshot();
  numeric.add_row({{ns.variables[0].variable,1000000001}},-inf,1000000001);
  auto nr=solve_native_auto(numeric,o);check(numeric.snapshot(),nr,oracle(numeric.snapshot()).first);
  // Presolve can now remove the redundant oversized row. A supplied start
  // deliberately skips transformations, still exercising numeric LP fallback.
  auto numeric_start=o;auto numeric_snapshot=numeric.snapshot();
  auto numeric_witness=oracle(numeric_snapshot).second;
  for(unsigned i=0;i<numeric_witness.size();++i)
    numeric_start.primal_start.push_back({numeric_snapshot.variables[i].variable,numeric_witness[i]});
  auto fallback=solve_native_auto(numeric,numeric_start);
  check(numeric_snapshot,fallback,oracle(numeric_snapshot).first);
  assert(fallback.backend=="Gecode native");
  if(capabilities(Backend::Highs).available){
    SolveOptions numerical;
    auto n=solve(numeric,numerical);
    assert(n.termination==Termination::Optimal && n.backend=="HiGHS");
  }
  Model moved;auto saved=std::move(moved);
  assert(solve_native_auto(moved,o).termination==Termination::InvalidModel);
  std::cout<<"Automatic native routing, exhaustive optima, starts and interruption checks passed\n";
}

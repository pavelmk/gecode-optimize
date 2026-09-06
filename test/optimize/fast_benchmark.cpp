/* Small solver regression panel. Build separately; run via fast_regression.py. */
#include <gecode/optimize/solve.hpp>
#include <gecode/optimize/constraints.hpp>
#include <gecode/optimize/validate.hpp>
#include <gecode/optimize/workflow.hpp>
#include <gecode/optimize/session.hpp>
#include <gecode/optimize/diagnostics.hpp>
#include <gecode/optimize/native.hpp>
#include <gecode/optimize/native_lp.hpp>
#include <gecode/optimize/native_search.hpp>
#include <gecode/optimize/pool.hpp>
#include <gecode/optimize/presolve.hpp>
#include <gecode/optimize/globals.hpp>
#include <gecode/optimize/c_api.h>
#include <gecode/optimize/relaxation.hpp>
#include <gecode/optimize/quadratic.hpp>
#include <gecode/optimize/lp_observations.hpp>
#include <gecode/optimize/lp_basis.hpp>
#include <gecode/optimize/lp_evidence.hpp>
#include <gecode/optimize/lp_sensitivity.hpp>
#include <gecode/optimize/native_neighborhoods.hpp>
#include <gecode/optimize/scenarios.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace O=Gecode::Optimize;
namespace fs=std::filesystem;
namespace {
constexpr double inf=std::numeric_limits<double>::infinity();
using Clock=std::chrono::steady_clock;
Clock::time_point deadline;
unsigned checks=0;
void require(bool value,const std::string& message){++checks;if(!value)throw std::runtime_error(message);}
void near(double a,double b){require(std::isfinite(a)&&std::isfinite(b)&&std::abs(a-b)<=1e-6,"oracle mismatch");}
O::SolveOptions options(){O::SolveOptions o;o.threads=1;o.random_seed=1701;o.relative_gap=o.absolute_gap=0;
  o.time_limit_seconds=std::max(0.0,std::chrono::duration<double>(deadline-Clock::now()).count());return o;}
O::SolveResult optimal(const O::Model& m,double expected){auto r=O::solve(m,options());
  require(r.termination==O::Termination::Optimal&&r.has_solution(),"expected validated numerical optimum: "+r.message);
  require(O::validate(m.snapshot(),r.values).valid,"independent original-model validation failed");
  near(*r.objective,expected);return r;}
std::string quote(const std::string& value){std::ostringstream out;out<<'"';for(unsigned char c:value){
  if(c=='"'||c=='\\')out<<'\\'<<c;else if(c<32)out<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<int(c)<<std::dec;else out<<c;}out<<'"';return out.str();}
struct Outcome {
  std::string status="optimal";
  std::vector<double> objectives;
  std::string backend={};
  std::string backend_version={};
  std::string guarantee="numerical";
};
Outcome run(const std::string& name,const fs::path& work,const fs::path& fixtures){
  if(name=="native_neighborhoods"){
    O::Model m;const auto x=m.add_binary(),y=m.add_binary(),z=m.add_binary();
    m.add_row({{z,1},{y,-1}},-inf,0);m.minimize({{x,100},{y,-20},{z,1}},-9);
    double oracle=inf;
    for(int a=0;a<2;++a)for(int b=0;b<2;++b)for(int c=0;c<2;++c)
      if(c<=b)oracle=std::min(oracle,100.0*a-20.0*b+c-9);
    O::NativeNeighborhoodOptions opts;opts.search.solve=options();
    opts.search.solve.backend=O::Backend::Native;opts.search.solve.guarantee=O::Guarantee::Exact;
    opts.search.solve.random_seed=0;opts.search.order=O::NativeSearchOrder::DepthFirst;
    opts.neighborhood.radius=1;opts.neighborhood.time_limit_seconds=opts.search.solve.time_limit_seconds;
    const auto answer=O::solve_native_neighborhoods(m,opts);
    const auto& r=answer.search.result;const auto& n=answer.neighborhood;
    require(r.termination==O::Termination::Optimal&&r.has_solution(),"native neighborhood optimum missing: "+r.message);
    require(O::validate(m.snapshot(),r.values).valid,"neighborhood original witness invalid");
    near(oracle,-29);near(*r.objective,oracle);near(r.value(x),0);near(r.value(y),1);near(r.value(z),0);
    require(r.best_bound&&*r.best_bound==oracle,"neighborhood global bound mismatch");
    require(n.attempts==1&&n.accepted_improvements==1&&n.status_attempts>0,"neighborhood produced no improvement");
    require(n.completed_status_calls<=n.status_attempts&&n.status_attempts<=opts.neighborhood.max_status_calls,
            "neighborhood local accounting mismatch");
    require(n.budget_nodes==answer.search.frontier.admitted_nodes+answer.search.branching.probe_status_calls+n.status_attempts&&
            n.budget_nodes==answer.search.branching.budget_nodes,"neighborhood shared accounting mismatch");
    Outcome out;out.objectives={*r.objective};out.backend=r.backend;out.backend_version=r.backend_version;out.guarantee="exact";
    return out;
  }
  if(name=="lp_sensitivity"){
    Outcome out;out.status="sensitivity_checked";
    for(const bool maximize:{false,true}){
      const double sign=maximize?-1:1;
      O::Model m;const auto x=m.add_continuous(),y=m.add_continuous();
      const auto row=m.add_row({{x,1},{y,1}},3,3);
      m.set_objective({{x,2*sign},{y,sign}},maximize?O::ObjectiveSense::Maximize:O::ObjectiveSense::Minimize,7);
      O::LpObservationOptions observed_options;observed_options.solve=options();
      const auto observed=O::solve_lp_observed(m,observed_options);
      require(observed.result.termination==O::Termination::Optimal&&observed.observations,
              "sensitivity source missing optimal observations");
      require(O::validate(m.snapshot(),observed.result.values).valid,"sensitivity source witness invalid");
      near(observed.result.value(x),0);near(observed.result.value(y),3);near(*observed.result.objective,7+3*sign);
      out.backend=observed.result.backend;out.backend_version=observed.result.backend_version;
      O::LpSensitivityOptions opts;opts.time_limit_seconds=options().time_limit_seconds;
      opts.parameters={O::LpObjectiveParameter{x},O::LpObjectiveParameter{y},O::LpEqualityRhsParameter{row}};
      const auto result=O::analyze_lp_sensitivity(observed,opts);
      require(result.completion==O::LpSensitivityCompletion::Complete&&result.sensitivity&&
              result.work.factor_setup_attempted&&result.work.basis_solves>=2,"sensitivity analysis incomplete");
      const auto& data=*result.sensitivity;
      require(data.checks().primal.valid&&data.checks().kkt.accepted&&data.checks().basis_point_matches,
              "sensitivity reference was not independently checked");
      const auto interval=[&](const O::LpSensitivityEntry* entry)->const O::LpParameterInterval&{
        require(entry&&entry->group.state==O::LpSensitivityState::Available&&entry->interval&&entry->interval->checks.accepted,
                "sensitivity interval unavailable");return *entry->interval;
      };
      const auto finite=[&](const O::LpRangeEnd& end,double value){
        require(end.kind==O::LpRangeEndKind::Finite&&end.value,"sensitivity finite endpoint missing");near(*end.value,value);
      };
      const auto infinite=[&](const O::LpRangeEnd& end,O::LpRangeEndKind kind){
        require(end.kind==kind&&!end.value,"sensitivity infinity tag/value mismatch");
      };
      const auto& cx=interval(data.objective(x));const auto& cy=interval(data.objective(y));
      const auto& rhs=interval(data.equality_rhs(row));
      if(maximize){infinite(cx.lower,O::LpRangeEndKind::NegativeInfinity);finite(cx.upper,-1);
        finite(cy.lower,-2);infinite(cy.upper,O::LpRangeEndKind::PositiveInfinity);
      }else{finite(cx.lower,1);infinite(cx.upper,O::LpRangeEndKind::PositiveInfinity);
        infinite(cy.lower,O::LpRangeEndKind::NegativeInfinity);finite(cy.upper,2);}
      finite(rhs.lower,0);infinite(rhs.upper,O::LpRangeEndKind::PositiveInfinity);
      require(cx.objective_slope&&cy.objective_slope&&rhs.objective_slope,"sensitivity objective slope missing");
      near(*cx.objective_slope,0);near(*cy.objective_slope,3);near(*rhs.objective_slope,sign);
      // Original feasible segment x=t,y=b-t: y-basic stays feasible iff b>=0;
      // its optimum value is 7+sign*b until the two cost coefficients tie.
      for(double b:{0.0,1.0,5.0})near(7+sign*b,*observed.result.objective+*rhs.objective_slope*(b-3));
      opts.time_limit_seconds=options().time_limit_seconds;opts.limits.max_work=0;
      const auto capped=O::analyze_lp_sensitivity(observed,opts);
      require(capped.reason==O::LpSensitivityReason::ResourceLimit&&!capped.work.factor_setup_attempted,
              "sensitivity quota did not reject before factorization");
      if(capped.sensitivity)for(const auto& e:capped.sensitivity->entries())
        require(e.group.state!=O::LpSensitivityState::Available&&!e.interval,"sensitivity quota exposed interval");
      m.set_bounds(row,4,4);
      require(data.revision()!=m.revision()&&data.original().observations->source().rows[row.id].lower==3,
              "sensitivity historical source changed");near(interval(data.equality_rhs(row)).anchor,3);
    }
    return out;
  }
  if(name=="lp_evidence"){
    Outcome out;out.status="evidence_checked";
    const auto history=[&](const O::LpEvidenceResult& result,const O::Model& source,std::size_t calls){
      require(result.completion==O::LpEvidenceCompletion::Complete&&result.evidence&&
              result.model_id==source.id()&&result.revision==source.revision()&&
              result.attempted_calls==calls,"LP evidence completion/identity/call count mismatch");
      require(result.evidence->stages().size()==calls,"LP evidence stages lost");
      for(const auto& stage:result.evidence->stages()){
        require(stage.attempted&&stage.auxiliary_model&&stage.auxiliary_result&&
                stage.auxiliary_model->model_id!=source.id(),"LP auxiliary provenance missing");
        const auto& raw=*stage.auxiliary_result;
        require(raw.model_id==stage.auxiliary_model->model_id&&raw.revision==stage.auxiliary_model->revision&&
                raw.backend=="HiGHS"&&raw.guarantee==O::Guarantee::Numerical&&
                raw.termination==O::Termination::Optimal&&stage.candidate_examined&&stage.auxiliary_check.valid,
                "LP auxiliary result was not independently checked in private coordinates");
        require(O::validate(*stage.auxiliary_model,raw.values).valid,"LP private witness invalid");
        out.backend=raw.backend;out.backend_version=raw.backend_version;
      }
    };
    for(const bool maximize:{false,true}){
      O::Model m;const auto x=m.add_continuous(),y=m.add_continuous(2,2);
      const auto row=m.add_row({{x,1},{y,-1}},-2,inf);
      m.set_objective({{x,maximize?2.0:-2.0},{y,3}},
        maximize?O::ObjectiveSense::Maximize:O::ObjectiveSense::Minimize,123);
      O::LpEvidenceOptions opts;opts.solve=options();opts.request=O::LpEvidenceRequest::PrimalRay;
      const auto recovered=O::analyze_lp_evidence(m,opts);history(recovered,m,2);
      const auto& e=*recovered.evidence;
      require(e.primal_ray().state==O::LpEvidenceState::Available&&
              e.farkas().state==O::LpEvidenceState::NotRequested,"LP primal evidence unavailable");
      const double bx=e.base_value(x),by=e.base_value(y),dx=e.direction_value(x),dy=e.direction_value(y);
      require(std::isfinite(bx)&&bx>=0&&bx-by>=-2,"LP base point violates original inequalities");
      near(by,2);near(dx,1);near(dy,0);
      near(e.primal_data().row_direction.at(row.id),dx-dy);
      require(e.primal_data().normalized_objective_slope.has_value(),"LP ray slope missing");
      near(*e.primal_data().normalized_objective_slope,-2);
      for(double t:{0.0,1.0,100.0}){
        require(bx+t*dx>=0&&bx+t*dx-(by+t*dy)>=-2,"LP ray leaves original row/bound region");
        near(by+t*dy,2);
      }
      m.set_bounds(x,0,0);
      near(e.direction_value(x),1);
      require(e.revision()!=m.revision()&&O::validate(e.source(),e.primal_data().base_point).valid,
              "LP evidence lost its historical original model");
    }
    O::Model infeasible;const auto x=infeasible.add_continuous(0,1);
    const auto row=infeasible.add_row({{x,1}},2,inf);infeasible.maximize({{x,7}},-45);
    O::LpEvidenceOptions opts;opts.solve=options();opts.request=O::LpEvidenceRequest::Farkas;
    const auto recovered=O::analyze_lp_evidence(infeasible,opts);history(recovered,infeasible,1);
    const auto& e=*recovered.evidence;
    require(e.farkas().state==O::LpEvidenceState::Available&&
            e.primal_ray().state==O::LpEvidenceState::NotRequested,"LP Farkas evidence unavailable");
    const auto& r=e.row_multiplier(row);const auto& c=e.column_multiplier(x);
    require(r.active&&c.active&&r.side==O::LpEvidenceSide::Lower&&c.side==O::LpEvidenceSide::Upper,
            "LP Farkas finite-side signs reversed");
    near(r.multiplier,1);near(c.multiplier,-1);near(r.multiplier+c.multiplier,0);
    near(r.contribution,2*r.multiplier);near(c.contribution,c.multiplier);
    require(e.farkas_data().contradiction_margin.has_value(),"LP contradiction margin missing");
    near(*e.farkas_data().contradiction_margin,1);
    near(r.contribution+c.contribution,1);
    // The signed inequalities sum to 0 >= 1. This is numerical evidence,
    // and neither that margin nor the ray slope is a source objective value.
    return out;
  }
  if(name=="scenario_batches"){
    O::Model m;const auto x=m.add_continuous(0,4);
    const auto row=m.add_row({{x,1}},1,inf);m.minimize({{x,2}},3);
    std::vector<O::ScenarioDefinition> definitions(4);
    definitions[1].variable_bounds={{x,3,{}}};
    definitions[2].objective_coefficients={{x,-1}};definitions[2].objective_offset=-7;
    definitions[3].row_bounds={{row,2,3}};
    const std::vector<double> expected={5,9,-11,7},values={1,3,4,2};
    Outcome out;
    for(auto reuse:{O::ScenarioReuse::Automatic,O::ScenarioReuse::Cold}){
      O::ScenarioBatchOptions opts;opts.solve=options();opts.reuse=reuse;
      const auto batch=O::solve_scenarios(m,definitions,opts);
      require(batch.all_resolved()&&batch.batch&&batch.outcomes.size()==4,"scenario batch did not complete: "+batch.message);
      for(std::size_t i=0;i<4;++i){
        const auto& outcome=batch.outcomes[i];
        require(outcome.result&&outcome.result->has_solution()&&outcome.check&&outcome.check->candidate_examined
          &&outcome.check->identity_valid&&outcome.check->objective_matches&&outcome.check->validation.valid,
          "scenario original witness check missing");
        const auto& r=*outcome.result;
        require(r.model_id==batch.batch->id()&&r.model_id!=m.id()&&r.revision==i+1,"scenario identities collapsed");
        near(*r.objective,expected[i]);near(batch.value(outcome.scenario,x),values[i]);
        if(reuse==O::ScenarioReuse::Automatic)out.objectives.push_back(*r.objective);
        out.backend=r.backend;out.backend_version=r.backend_version;
      }
      if(reuse==O::ScenarioReuse::Automatic)require(batch.reuse_statistics.model_loads==1,"scenario compatible edits reloaded the model");
    }
    return out;
  }
  if(name=="native_regular"){
    O::Model m;std::vector<O::Variable> word;
    for(int i=0;i<3;++i)word.push_back(m.add_integer(-1,1));
    constexpr std::uint64_t odd=1000000000;
    O::add_regular(m,word,odd+1,0,{{0,-1,0},{0,1,odd},{odd,-1,odd},{odd,1,0}},{0});
    double lower=inf,upper=-inf;
    for(int a:{-1,1})for(int b:{-1,1})for(int c:{-1,1})
      if(((a==1)+(b==1)+(c==1))%2==0){lower=std::min(lower,double(a+b+c));upper=std::max(upper,double(a+b+c));}
    Outcome out;out.guarantee="exact";
    for(auto sense:{O::ObjectiveSense::Minimize,O::ObjectiveSense::Maximize}){
      m.set_objective({{word[0],1},{word[1],1},{word[2],1}},sense);
      auto opts=options();opts.random_seed=0;opts.guarantee=O::Guarantee::Exact;
      const auto r=O::solve(m,opts);
      require(r.termination==O::Termination::Optimal&&r.has_solution()&&r.guarantee==O::Guarantee::Exact,"Regular solve failed: "+r.message);
      int positives=0;
      for(auto x:word){const auto v=r.value(x);require(v==-1||v==1,"missing Regular transition admitted zero");positives+=v==1;}
      require(positives%2==0&&r.objective==(sense==O::ObjectiveSense::Minimize?lower:upper)&&r.best_bound==r.objective,
              "Regular witness or optimum differs from signed parity enumeration");
      out.backend=r.backend;out.backend_version=r.backend_version;out.objectives.push_back(*r.objective);
    }
    return out;
  }
  if(name=="lp_observations"){
    const auto caps=O::lp_observation_capabilities();
    require(caps.available&&caps.duals&&caps.basis_export,"LP observations unavailable");
    Outcome out;
    for(const bool maximize:{false,true}){
      O::Model m;auto x=m.add_continuous(),y=m.add_continuous();
      auto row=m.add_row({{x,1},{y,1}},maximize?-inf:4,maximize?4:inf);
      if(maximize)m.maximize({{x,2},{y,3}},7);else m.minimize({{x,2},{y,3}},7);
      O::LpObservationOptions opts;opts.solve=options();auto solved=O::solve_lp_observed(m,opts);
      const auto& r=solved.result;
      require(r.termination==O::Termination::Optimal&&r.has_solution()&&solved.observations,
              "LP observations solve incomplete: "+r.message);
      const auto& obs=*solved.observations;
      require(O::validate(m.snapshot(),r.values).valid,"LP observation original witness invalid");
      // Independent analytic primal and dual witnesses: (4,0), pi=2 for min;
      // (0,4), pi=3 for max. Both have zero primal-dual gap, including offset.
      const double pi=maximize?3:2,expected=maximize?19:15;
      near(r.value(x),maximize?0:4);near(r.value(y),maximize?4:0);near(*r.objective,expected);
      require(obs.primal_rows().state==O::LpObservationState::Available
              &&obs.dual_point().state==O::LpObservationState::Available
              &&obs.basis().state==O::LpObservationState::Available&&obs.checks().accepted,
              "LP observation group unavailable or independent KKT check failed");
      const auto& activity=obs.row(row);const auto& cx=obs.column(x);const auto& cy=obs.column(y);
      require(activity.activity&&activity.dual&&cx.reduced_cost&&cy.reduced_cost
              &&activity.basis&&cx.basis&&cy.basis,"LP original coordinates missing");
      near(*activity.activity,4);near(*activity.dual,pi);
      near(*cx.reduced_cost,2-pi);near(*cy.reduced_cost,3-pi);
      require(maximize?(!activity.lower_slack&&activity.upper_slack):
                       (activity.lower_slack&&!activity.upper_slack),"LP infinite side has a slack");
      near(maximize?*activity.upper_slack:*activity.lower_slack,0);
      require(obs.checks().dual_objective_estimate&&obs.checks().normalized_gap,
              "LP dual objective or gap missing");
      near(*obs.checks().dual_objective_estimate,expected);near(*obs.checks().normalized_gap,0);
      require(obs.metadata().backend==r.backend&&obs.metadata().backend_version==r.backend_version,
              "LP observation backend attribution mismatch");
      O::LpBasisSolveOptions reuse;reuse.observations.solve=options();reuse.basis=O::make_lp_basis(obs);
      const auto started=O::solve_lp_with_basis(m,reuse);
      require(started.submission.backend_attempted&&
              (started.submission.state==O::LpBasisSubmissionState::Accepted||
               started.submission.state==O::LpBasisSubmissionState::Repaired),"LP basis was not submitted");
      require(started.observed.result.termination==O::Termination::Optimal&&started.observed.result.has_solution()
              &&O::validate(m.snapshot(),started.observed.result.values).valid,"LP basis solve original witness invalid");
      near(*started.observed.result.objective,expected);
      out.objectives.push_back(*r.objective);out.backend=r.backend;out.backend_version=r.backend_version;
    }return out;
  }
  if(name=="lp_min_offset"){
    O::Model m;auto x=m.add_continuous(),y=m.add_continuous();
    m.add_row({{x,1},{y,1}},5,inf);m.add_row({{x,2},{y,1}},6,inf);m.minimize({{x,3},{y,2}},-7);
    auto r=optimal(m,4);near(r.value(x),1);near(r.value(y),4);return {"optimal",{*r.objective}};
  }
  if(name=="lp_max_offset"){
    O::Model m;auto x=m.add_continuous(),y=m.add_continuous();
    m.add_row({{x,1},{y,2}},-inf,6);m.add_row({{x,2},{y,1}},-inf,6);m.maximize({{x,2},{y,3}},5);
    auto r=optimal(m,15);near(r.value(x),2);near(r.value(y),2);return {"optimal",{*r.objective}};
  }
  if(name=="bounded_integer"){
    O::Model m;const auto variables=m.add_variables({{O::VariableType::Integer,-3,7,"n"},{O::VariableType::Integer,0,5,"k"}});
    auto n=variables[0],k=variables[1];require(m.revision()==1,"bulk variable posting was not one atomic revision");
    O::SparseRowBatch rows;rows.columns={k,n};rows.row_start={0,2};rows.column={1,0};
    rows.coefficient={2,3};rows.lower={7};rows.upper={inf};m.add_rows_sparse(rows);
    require(m.revision()==2,"CSR row posting was not one atomic revision");m.minimize({{n,4},{k,5}},2);
    double oracle=inf;for(int i=-3;i<=7;++i)for(int j=0;j<=5;++j)if(2*i+3*j>=7)oracle=std::min(oracle,4.0*i+5*j+2);
    auto r=optimal(m,oracle);return {"optimal",{*r.objective}};
  }
  if(name=="mixed_recourse"){
    Outcome out;
    for(const int demand:{3,7,11,17,19,23}){
      O::Model m;auto open=m.add_binary(),n=m.add_integer(0,5),y=m.add_continuous(0,25);
      m.add_row({{y,1},{open,-25}},-inf,0);m.add_row({{n,3},{y,1}},demand,inf);
      m.minimize({{open,7},{n,3},{y,1.5}},-4);
      double oracle=inf;for(int b=0;b<=1;++b)for(int k=0;k<=5;++k){const double recourse=std::max(0,demand-3*k);
        if(recourse<=25*b)oracle=std::min(oracle,-4+7*b+3*k+1.5*recourse);}
      auto r=optimal(m,oracle);near(r.value(y),std::max(0.0,demand-3*r.value(n)));out.objectives.push_back(*r.objective);
    }return out;
  }
  if(name=="indicators_boolean"){
    O::Model m;auto b=m.add_binary(),one=m.add_binary(),both=m.add_binary(),either=m.add_binary();auto q=m.add_continuous(0,10);
    m.set_bounds(one,1,1);O::add_boolean_and(m,both,{b,one});O::add_boolean_or(m,either,{b,both});
    O::add_indicator(m,b,true,{{q,1}},7,inf);O::add_indicator(m,b,false,{{q,1}},-inf,3);
    m.minimize({{both,-20},{q,1}});auto r=optimal(m,-13);near(r.value(b),1);near(r.value(q),7);near(r.value(either),1);
    return {"optimal",{*r.objective}};
  }
  if(name=="semis"){
    O::Model m;auto sc=m.add_variable(O::VariableType::SemiContinuous,3,8),si=m.add_variable(O::VariableType::SemiInteger,2.5,7);
    auto a=m.add_row({{sc,1}},1,inf),b=m.add_row({{si,1}},1,inf);m.minimize({{sc,2},{si,1}},-1);
    auto active=optimal(m,8);near(active.value(sc),3);near(active.value(si),3);
    m.set_bounds(a,0,inf);m.set_bounds(b,0,inf);auto zero=optimal(m,-1);near(zero.value(sc),0);near(zero.value(si),0);
    return {"optimal",{*active.objective,*zero.objective}};
  }
  if(name=="multiobjective"){
    O::Model m;auto x=m.add_integer(0,4),y=m.add_integer(0,4);m.add_row({{x,1},{y,1}},4,inf);m.minimize({{x,7}});
    O::ObjectiveData first{{{x,1},{y,1}},10,O::ObjectiveSense::Minimize};
    O::ObjectiveData second{{{y,1}},-3,O::ObjectiveSense::Maximize};
    auto opts=options();opts.primal_start={{x,3}};
    auto r=O::solve_lexicographic(m,{{first,0,0,"total"},{second,0,0,"prefer_y"}},opts);
    require(r.completed_numerically()&&r.has_solution()&&r.objective_values.size()==2,"lexicographic workflow incomplete");
    near(r.objective_values[0],14);near(r.objective_values[1],1);near(r.final_solution.value(x),0);near(r.final_solution.value(y),4);
    require(O::validate(m.snapshot(),r.final_solution.values).valid,"lexicographic original validation failed");
    return {"optimal",r.objective_values};
  }
  if(name=="infeasible"){
    O::Model m;auto x=m.add_integer(0,0.5);m.add_row({{x,1}},0.25,inf);auto r=O::solve(m,options());
    require(r.termination==O::Termination::Infeasible&&!r.has_solution(),"infeasible discrete interval misclassified");return {"infeasible",{}};
  }
  if(name=="unbounded"){
    O::Model m;auto x=m.add_continuous(-inf,inf);m.minimize({{x,1}});auto r=O::solve(m,options());
    require(r.termination==O::Termination::Unbounded,"explicit improving ray misclassified");return {"unbounded",{}};
  }
  if(name=="edits_io"){
    O::Model m;auto x=m.add_continuous(4,20,"quantity");m.minimize({{x,2}},-3);auto before=optimal(m,5);
    m.set_bounds(x,5,20);auto after=optimal(m,7);near(before.value(x),4);require(after.revision>before.revision,"edit revision not advanced");
    Outcome out{"optimal",{*before.objective,*after.objective}};
    for(const auto& ext:{".lp",".mps"}){const auto path=work/(std::string("edited")+ext);O::write_model(m,path.string());auto copy=O::read_model(path.string());
      auto r=optimal(copy,7);require(copy.id()!=m.id(),"import reused model identity");out.objectives.push_back(*r.objective);}
    auto cancellation=O::read_model((fixtures/"cancellation.lp").string());auto r=optimal(cancellation,-1);out.objectives.push_back(*r.objective);
    auto precision=O::read_model((fixtures/"precision.lp").string());
    require(!O::validate(precision.snapshot(),{1},0,0).valid&&O::validate(precision.snapshot(),{2},0,0).valid,"precision witnesses changed");
    for(const auto& ext:{".lp",".mps"}){const auto path=work/(std::string("precision")+ext);O::write_model(precision,path.string());auto copy=O::read_model(path.string());
      require(!O::validate(copy.snapshot(),{1},0,0).valid&&O::validate(copy.snapshot(),{2},0,0).valid,"roundtrip lost precision");}
    return out;
  }
  if(name=="limit_contracts"){
    O::Model m;auto x=m.add_continuous(1,2);m.minimize({{x,1}});auto opts=options();opts.time_limit_seconds=0;
    require(O::solve(m,opts).termination==O::Termination::TimeLimit,"zero deadline ignored");
    opts=options();opts.cancellation=std::make_shared<O::CancellationToken>();opts.cancellation->cancel();
    require(O::solve(m,opts).termination==O::Termination::Cancelled,"cancellation ignored");
    opts=options();opts.guarantee=O::Guarantee::Certified;
    require(O::solve(m,opts).termination==O::Termination::Unsupported,"numerical result mislabeled certified");
    return {"contract_pass",{}};
  }
  if(name=="session_reoptimization"){
    O::Model m;auto x=m.add_continuous(0,100),y=m.add_continuous(0,100);
    const auto demand=m.add_row({{x,1},{y,1}},4,inf);m.minimize({{x,2},{y,3}},-3);
    O::SolveSession session;Outcome out;
    const auto check=[&](O::SolveSession& state,const O::Model& model,double expected,O::SolveOptions opts){
      auto r=state.solve(model,opts);
      require(r.termination==O::Termination::Optimal&&r.has_solution(),"session did not reach validated optimum: "+r.message);
      require(O::validate(model.snapshot(),r.values).valid,"session original validation failed");near(*r.objective,expected);
      out.objectives.push_back(*r.objective);out.backend=r.backend;out.backend_version=r.backend_version;return r;
    };
    const auto first=check(session,m,5,options());
    m.set_bounds(demand,8,inf);check(session,m,13,options());
    m.set_bounds(x,0,3);check(session,m,18,options());
    m.maximize({{x,-4},{y,-2}},10);check(session,m,-6,options());
    const auto stats=session.statistics();
    require(stats.model_loads==1&&stats.incremental_updates==3&&stats.basis_warm_starts>=1,"session failed compatible LP state reuse");
    near(first.value(x),4);near(*first.objective,5);require(first.revision<m.revision(),"historical session revision changed");
    O::Model mip;auto z=mip.add_integer(0,5);mip.minimize({{z,1}},2);O::SolveSession integer;
    check(integer,mip,2,options());mip.set_objective_offset(3);
    auto retained=check(integer,mip,3,options());
    require(retained.start_submitted&&integer.statistics().incumbent_starts==1,"feasible prior MIP witness was not revalidated/submitted");
    mip.set_bounds(z,2,5);auto invalidated=check(integer,mip,5,options());
    require(!invalidated.start_submitted&&integer.statistics().incumbent_starts==1,"infeasible prior witness was reused after bounds edit");
    auto explicit_start=options();explicit_start.primal_start={{z,4}};
    auto explicit_result=check(integer,mip,5,explicit_start);
    require(explicit_result.start_submitted&&integer.statistics().incumbent_starts==1,"explicit start did not take precedence");
    return out;
  }
  if(name=="diagnostics_groups"){
    Outcome out{"irreducible",{}};
    const auto diagnose=[&](const O::Model& model){
      O::ConflictOptions opts;opts.solve=options();opts.retain_deletion_witnesses=true;
      auto result=O::analyze_conflict(model,opts);
      require(result.irreducible()&&result.infeasibility_established&&result.termination==O::Termination::Infeasible,
              "conflict analysis failed: "+result.message);
      require(result.guarantee==O::Guarantee::Numerical&&result.model_id==model.id()&&result.revision==model.revision(),"conflict evidence/identity mismatch");
      out.backend=result.backend;out.backend_version=result.backend_version;
      // Reconstruct each deletion from a free system, independently of the
      // filter's relaxation code. Only these cases' row/bound/integrality groups
      // are permitted, so unexpected coarse grouping cannot pass.
      const auto original=model.snapshot();
      for(std::size_t omitted=0;omitted<result.groups.size();++omitted){
        auto subset=original;subset.objective={};
        for(auto& variable:subset.variables){variable.type=O::VariableType::Continuous;variable.lower=-inf;variable.upper=inf;}
        for(auto& row:subset.rows){row.active=false;row.terms.clear();}
        for(std::size_t i=0;i<result.groups.size();++i)if(i!=omitted){const auto& group=result.groups[i];
          if(group.kind==O::ConflictGroupKind::Row){require(group.row.has_value(),"row attribution missing");subset.rows.at(group.row->id)=original.rows.at(group.row->id);}
          else {require(group.variable.has_value(),"domain attribution missing");const auto id=group.variable->id;
            require(group.variable->model_id==model.id(),"foreign conflict variable");
            if(group.kind==O::ConflictGroupKind::LowerBound)subset.variables.at(id).lower=original.variables.at(id).lower;
            else if(group.kind==O::ConflictGroupKind::UpperBound)subset.variables.at(id).upper=original.variables.at(id).upper;
            else if(group.kind==O::ConflictGroupKind::Integrality)subset.variables.at(id).type=O::VariableType::Integer;
            else require(false,"unexpected conflict grouping");}
        }
        require(result.groups[omitted].necessity_verified,"conflict group necessity not established");
        require(O::validate(subset,result.groups[omitted].deletion_witness).valid,"conflict deletion witness fails independent reconstruction");
      }
      return result;
    };
    O::Model bound;auto x=bound.add_continuous(0,10);auto demand=bound.add_row({{x,1}},11,inf);bound.maximize({{x,7}},-5);
    const auto before=bound.snapshot();auto result=diagnose(bound);
    require(result.groups.size()==2&&result.groups[0].kind==O::ConflictGroupKind::Row&&result.groups[0].row->id==demand.id&&
            result.groups[1].kind==O::ConflictGroupKind::UpperBound&&*result.groups[1].variable==x,"wrong bound/row conflict");
    require(bound.revision()==before.revision&&bound.row(demand).active&&bound.snapshot().objective.offset==-5,"diagnostics mutated original model");
    O::Model integral;auto n=integral.add_integer(0.25,0.75);result=diagnose(integral);
    require(result.groups.size()==3&&result.groups[0].kind==O::ConflictGroupKind::LowerBound&&
            result.groups[1].kind==O::ConflictGroupKind::UpperBound&&result.groups[2].kind==O::ConflictGroupKind::Integrality,"fractional interval integrality conflict lost");
    for(const auto& group:result.groups)require(group.variable&&*group.variable==n,"wrong integrality conflict variable");
    return out;
  }
  if(name=="native_exact_reified"){
    O::Model m;auto b=m.add_binary(),n=m.add_integer(-3,3),semi=m.add_variable(O::VariableType::SemiInteger,2,4);
    auto on=O::add_indicator(m,b,true,{{n,2},{semi,-1},{b,1}},-2,1);
    O::add_indicator(m,b,false,{{n,1},{semi,1}},-inf,2);
    require(on.inactive_gate.has_value(),"expected exposed inactive gate");
    const std::vector<O::Term> objective{{n,-2},{semi,3},{b,-4},{*on.inactive_gate,1}};
    double lower=inf,upper=-inf;
    for(int active=0;active<=1;++active)for(int count=-3;count<=3;++count)for(int amount:{0,2,3,4}){
      const int row=2*count-amount+active;
      if((active&& (row < -2||row > 1))||(!active&&count+amount>2))continue;
      const double value=-2*count+3*amount-4*active+(1-active)-7;
      lower=std::min(lower,value);upper=std::max(upper,value);
    }
    Outcome out;out.guarantee="exact";
    for(auto sense:{O::ObjectiveSense::Minimize,O::ObjectiveSense::Maximize}){
      m.set_objective(objective,sense,-7);auto opts=options();opts.backend=O::Backend::Native;opts.guarantee=O::Guarantee::Exact;opts.random_seed=0;
      auto r=O::solve(m,opts);
      require(r.termination==O::Termination::Optimal&&r.has_solution()&&r.guarantee==O::Guarantee::Exact,"native Exact route failed: "+r.message);
      require(r.backend=="Gecode native"&&!r.backend_version.empty(),"native route misattributed to another backend");
      require(O::validate(m.snapshot(),r.values,0,0).valid,"native original witness failed");
      const auto active=r.value(b),count=r.value(n),amount=r.value(semi);
      require((active==0||active==1)&&count==std::trunc(count)&&(amount==0||amount==2||amount==3||amount==4),"native integer domains changed");
      require(active==1?(2*count-amount+active>=-2&&2*count-amount+active<=1):count+amount<=2,"native reification differs from logical oracle");
      require(r.value(*on.inactive_gate)==1-active,"native exposed gate mapping failed");
      require(*r.objective==(sense==O::ObjectiveSense::Minimize?lower:upper)&&r.best_bound==r.objective&&r.absolute_gap==0,"native exact objective/bound differs from exhaustive oracle");
      out.objectives.push_back(*r.objective);out.backend=r.backend;out.backend_version=r.backend_version;
    }
    return out;
  }
  if(name=="native_globals"){
    O::Model m;std::vector<O::Variable> starts,successors;
    for(int i=0;i<3;++i){starts.push_back(m.add_integer(0,4));successors.push_back(m.add_integer(-2,0));}
    auto index=m.add_integer(-1,1),selected=m.add_integer(0,4);
    O::add_all_different(m,starts);
    O::add_cumulative(m,starts,{2,2,2},{1,1,1},1);
    O::add_table(m,{starts[0],starts[1]},{{0,2},{2,4},{4,0}});
    O::add_element(m,index,starts,selected,-1);
    O::add_circuit(m,successors,-2);
    double lower=inf,upper=-inf;
    // Enumerate original schedules and the two possible three-node cycles.
    for(int a=0;a<=4;++a)for(int b=0;b<=4;++b)for(int c=0;c<=4;++c){
      if(std::abs(a-b)<2||std::abs(a-c)<2||std::abs(b-c)<2)continue;
      if(!((a==0&&b==2)||(a==2&&b==4)||(a==4&&b==0)))continue;
      for(int chosen:{a,b,c})for(int next:{-1,0}){
        const double objective=4*a+2*b+c+3*chosen+next;
        lower=std::min(lower,objective);upper=std::max(upper,objective);
      }
    }
    Outcome out;out.guarantee="exact";
    for(auto sense:{O::ObjectiveSense::Minimize,O::ObjectiveSense::Maximize}){
      m.set_objective({{starts[0],4},{starts[1],2},{starts[2],1},{selected,3},{successors[0],1}},sense);
      auto opts=options();opts.random_seed=0;opts.guarantee=O::Guarantee::Exact;
      // Auto must preserve typed globals and select the native compiler.
      auto r=O::solve(m,opts);
      require(r.termination==O::Termination::Optimal&&r.has_solution()&&r.guarantee==O::Guarantee::Exact,"native global solve failed: "+r.message);
      require(r.backend=="Gecode native"&&!r.backend_version.empty(),"global dispatch lost native provenance");
      require(O::validate(m.snapshot(),r.values,0,0).valid,"native global witness failed original predicates");
      require(*r.objective==(sense==O::ObjectiveSense::Minimize?lower:upper)&&r.best_bound==r.objective,"native global objective differs from exhaustive schedule oracle");
      out.backend=r.backend;out.backend_version=r.backend_version;out.objectives.push_back(*r.objective);
    }
    return out;
  }
  if(name=="c_api_ownership"){
    struct Owners {gecode_opt_handle model=0,session=0,first=0,second=0;
      ~Owners(){if(first)gecode_opt_v1_result_destroy(first);if(second)gecode_opt_v1_result_destroy(second);
        if(session)gecode_opt_v1_session_destroy(session);if(model)gecode_opt_v1_model_destroy(model);}} owned;
    const auto ok=[](int error){require(error==GECODE_OPT_OK,std::string("C ABI error: ")+gecode_opt_v1_last_error());};
    require(gecode_opt_v1_abi_version()==1,"wrong C ABI version");
    ok(gecode_opt_v1_model_create(&owned.model));ok(gecode_opt_v1_session_create(&owned.session));
    gecode_opt_id x,y,row;
    ok(gecode_opt_v1_model_add_variable(owned.model,GECODE_OPT_INTEGER,0,5,"units",&x));
    ok(gecode_opt_v1_model_add_variable(owned.model,GECODE_OPT_CONTINUOUS,0,5,"recourse",&y));
    gecode_opt_term terms[]={{x,1},{y,1}};
    ok(gecode_opt_v1_model_add_row(owned.model,terms,2,2.5,inf,"demand",&row));
    terms[0].coefficient=2;terms[1].coefficient=3;
    ok(gecode_opt_v1_model_set_objective(owned.model,terms,2,GECODE_OPT_MINIMIZE,.25));
    gecode_opt_options_v1 opts;ok(gecode_opt_v1_options_default(&opts,sizeof opts));
    opts.backend=GECODE_OPT_HIGHS;opts.time_limit_seconds=options().time_limit_seconds;opts.relative_gap=opts.absolute_gap=0;
    ok(gecode_opt_v1_session_solve(owned.session,owned.model,&opts,&owned.first));
    ok(gecode_opt_v1_model_set_variable_bounds(owned.model,x,3,5));
    opts.time_limit_seconds=options().time_limit_seconds;
    ok(gecode_opt_v1_session_solve(owned.session,owned.model,&opts,&owned.second));
    ok(gecode_opt_v1_session_destroy(owned.session));owned.session=0;
    ok(gecode_opt_v1_model_destroy(owned.model));owned.model=0;
    Outcome out;
    for(auto pair:{std::pair<gecode_opt_handle,double>{owned.first,5.75},{owned.second,6.25}}){
      gecode_opt_result_info_v1 info;ok(gecode_opt_v1_result_info(pair.first,&info,sizeof info));
      require(info.termination==GECODE_OPT_OPTIMAL&&info.has_solution&&info.solution_validated,"C ABI historical result lost validity");
      int32_t present=0;double objective=0;ok(gecode_opt_v1_result_number(pair.first,GECODE_OPT_OBJECTIVE,&present,&objective));
      require(present,"C ABI objective absent");near(objective,pair.second);out.objectives.push_back(objective);
      double xv=0,yv=0;ok(gecode_opt_v1_result_value(pair.first,x,&xv));ok(gecode_opt_v1_result_value(pair.first,y,&yv));
      near(xv,pair.first==owned.first?2:3);near(yv,pair.first==owned.first?.5:0);
      near(2*xv+3*yv+.25,objective);
    }
    return out;
  }
  if(name=="feasibility_repair"){
    O::Model m;auto x=m.add_continuous(0,1),y=m.add_continuous(0,1);
    const auto demand=m.add_row({{x,1},{y,1}},3,inf,"demand");m.minimize({{y,1}},-2);
    const auto original=m.snapshot();O::RelaxationOptions opts;opts.solve=options();
    opts.rows={{demand,O::RelaxationSide::Lower,1}};opts.optimize_original_objective=true;
    auto repair=O::relax_feasibility(m,opts);
    require(repair.termination==O::Termination::Optimal&&repair.has_repair()&&repair.minimum_violation_established&&repair.original_objective_optimized,"repair workflow failed: "+repair.message);
    near(*repair.minimum_weighted_violation,1);near(*repair.weighted_violation,1);near(*repair.original_objective,-1);
    require(repair.source_model_id==m.id()&&repair.source_revision==m.revision()&&repair.private_model&&repair.private_model->model_id!=m.id(),"repair source/private identity collapsed");
    require(m.revision()==original.revision&&m.row(demand).lower==3,"repair mutated original model");
    require(!repair.original_validation.valid&&!O::validate(original,repair.original_values).valid,"infeasible original point relabeled feasible");
    require(O::validate(*repair.private_model,repair.workflow.final_solution.values).valid,"private repair failed original checking");
    require(repair.items.size()==1&&repair.items[0].source_row&&repair.items[0].source_row->id==demand.id,"repair row attribution lost");
    near(*repair.items[0].violation,1);
    // A zero-violation minimum leaves several repairs; phase two must select y=0.
    m.set_bounds(demand,1,inf);opts.solve=options();auto feasible=O::relax_feasibility(m,opts);
    require(feasible.has_repair()&&feasible.original_objective_optimized&&feasible.original_validation.valid,"zero violation refinement failed");
    near(*feasible.weighted_violation,0);near(*feasible.original_objective,-2);
    return {"optimal",{*repair.weighted_violation,*repair.original_objective,*feasible.weighted_violation,*feasible.original_objective}};
  }
  if(name=="native_checked_lp") {
    O::Model m;auto n=m.add_integer(-3,7),k=m.add_integer(0,5);
    m.add_row({{n,2},{k,3}},7,12);
    double low=inf,high=-inf;
    for(int x=-3;x<=7;++x)for(int y=0;y<=5;++y)if(2*x+3*y>=7&&2*x+3*y<=12) {
      low=std::min(low,4.0*x+5*y+2);high=std::max(high,4.0*x+5*y+2);
    }
    Outcome out;out.guarantee="exact";
    for(bool maximum:{false,true}) {
      m.set_objective({{n,4},{k,5}},maximum?O::ObjectiveSense::Maximize:O::ObjectiveSense::Minimize,2);
      O::NativeLpOptions opts;opts.solve=options();opts.solve.random_seed=0;opts.solve.guarantee=O::Guarantee::Exact;
      opts.frequency=O::NativeLpFrequency::AfterBoundChanges;opts.bound_change_interval=2;
      const auto solved=O::solve_native_lp(m,opts);const auto& r=solved.result;
      require(r.termination==O::Termination::Optimal&&r.has_solution(),"native LP solve failed: "+r.message);
      require(r.objective==std::optional<double>(maximum?high:low)&&r.best_bound==r.objective&&r.absolute_gap==0,"native LP completion disagrees with enumeration");
      require(O::validate(m.snapshot(),r.values).valid,"native LP original witness invalid");
      require(solved.relaxation.lp_calls>0&&solved.relaxation.valid_bounds>0,"native LP bypassed numerical relaxation or checked deductions");
      out.objectives.push_back(*r.objective);out.backend=r.backend;out.backend_version=r.backend_version;
    }
    return out;
  }
  if(name=="solution_pool") {
    O::Model m;auto n=m.add_integer(0,2),q=m.add_continuous(0,10);
    m.add_row({{n,2},{q,1}},4,inf);m.minimize({{n,1},{q,1}},-1);
    O::PoolOptions opts;opts.solve=options();opts.max_solutions=5;
    const auto all=O::solve_pool(m,opts);
    require(all.exhausted()&&all.termination==O::Termination::Optimal&&all.entries.size()==3&&all.ranked_prefix==3,"projection pool exhaustion failed: "+all.message);
    require(all.attempts.size()==4&&all.attempts.back().termination==O::Termination::Infeasible,"pool exhaustion evidence missing");
    Outcome out;
    for(std::size_t i=0;i<all.entries.size();++i) {
      const auto& entry=all.entries[i];const auto& r=entry.solution;
      require(entry.rank_established&&entry.projection_values==std::vector<std::int64_t>{2-static_cast<std::int64_t>(i)},"projection pool rank/identity mismatch");
      require(r.model_id==m.id()&&r.revision==m.revision()&&r.has_solution()&&O::validate(m.snapshot(),r.values).valid,"pool original witness lost");
      require(r.termination==O::Termination::Unknown&&!r.best_bound&&!r.absolute_gap,"restricted pool optimum mislabeled original scalar optimum");
      near(*r.objective,1+i);near(r.value(n),2-i);near(r.value(q),2*i);
      out.objectives.push_back(*r.objective);out.backend=r.backend;out.backend_version=r.backend_version;
    }
    opts.solve=options();opts.max_solutions=2;const auto limited=O::solve_pool(m,opts);
    require(!limited.exhausted()&&limited.completion==O::PoolCompletion::RequestedLimit&&limited.termination==O::Termination::SolutionLimit&&limited.entries.size()==2,"requested pool limit falsely implied exhaustion");
    return out;
  }
  if(name=="integer_presolve") {
    Outcome out;out.guarantee="exact";
    for(bool maximum:{false,true}) {
      O::Model m;const auto removed=m.add_integer(-3,3);m.remove(removed);
      const auto fixed=m.add_integer(2,2),y=m.add_integer(-2,2);
      m.add_row({{fixed,3},{y,-2}},4,8,"range");
      m.set_objective({{fixed,-3},{y,2}},maximum?O::ObjectiveSense::Maximize:O::ObjectiveSense::Minimize,11);
      O::PresolveOptions presolve;presolve.time_limit_seconds=options().time_limit_seconds;
      const auto prepared=O::presolve_integer(m,presolve);
      require(prepared.status==O::PresolveStatus::Fixpoint&&prepared.model&&prepared.fixed_variables==1,"integer presolve did not produce equivalent fixed substitution");
      require(prepared.model->reduced().model_id!=m.id(),"presolve reduced/original identities collapsed");
      auto opts=options();opts.backend=O::Backend::Native;opts.guarantee=O::Guarantee::Exact;opts.random_seed=0;
      const auto reduced=O::solve_native(prepared.model->reduced(),opts);
      require(reduced.termination==O::Termination::Optimal&&reduced.has_solution(),"presolved native solve failed");
      const auto restored=prepared.model->postsolve(reduced);
      require(restored.exact_witness_validated&&restored.solution.has_solution(),"presolve original reconstruction failed");
      const auto& r=restored.solution;
      require(r.model_id==m.id()&&r.revision==m.revision()&&!r.active_variables[removed.id],"postsolve historical identity/mask lost");
      require(r.termination==O::Termination::Unknown&&!r.best_bound&&!r.absolute_gap,"postsolve copied reduced scalar proof without coordination");
      double oracle=maximum?-inf:inf;for(int value=-2;value<=2;++value)if(4<=6-2*value&&6-2*value<=8)
        oracle=maximum?std::max(oracle,5.0+2*value):std::min(oracle,5.0+2*value);
      require(r.objective==std::optional<double>(oracle)&&r.value(fixed)==2,"postsolve offset/substitution disagrees with original enumeration");
      require(O::validate(prepared.model->original(),r.values,0,0).valid,"postsolve exact original witness rejected");
      out.objectives.push_back(*r.objective);out.backend=r.backend;out.backend_version=r.backend_version;
    }
    return out;
  }
  if(name=="native_frontier_bounds") {
    Outcome out;out.guarantee="exact";
    for(bool maximum:{false,true}) {
      O::Model m;auto x=m.add_binary(),y=m.add_binary();
      m.set_objective({{x,maximum?-2.0:2.0},{y,maximum?-1.0:1.0}},
        maximum?O::ObjectiveSense::Maximize:O::ObjectiveSense::Minimize,maximum?17:-17);
      O::NativeSearchOptions opts;opts.solve=options();opts.solve.random_seed=0;opts.solve.guarantee=O::Guarantee::Exact;
      const auto complete=O::solve_native_search(m,opts);
      const auto optimum=maximum?17.0:-17.0;
      require(complete.result.termination==O::Termination::Optimal&&complete.result.has_solution()&&complete.result.objective==optimum&&complete.result.best_bound==optimum,"best-bound frontier completion failed");
      opts.order=O::NativeSearchOrder::DepthFirst;opts.solve=options();opts.solve.random_seed=0;
      opts.solve.guarantee=O::Guarantee::Exact;opts.solve.node_limit=4;
      const auto interrupted=O::solve_native_search(m,opts);const auto& r=interrupted.result;
      require(r.termination==O::Termination::NodeLimit&&r.has_solution()&&r.objective==(maximum?15:-15),"frontier failed to retain timely incumbent at quota");
      require(r.best_bound==optimum&&r.absolute_gap==2&&interrupted.frontier.unresolved_regions>=2,"frontier lost the better unresolved sibling bound");
      require(O::validate(m.snapshot(),r.values,0,0).valid&&interrupted.relaxation.lp_calls==0,"native frontier witness or route changed");
      out.objectives.insert(out.objectives.end(),{*complete.result.objective,*r.objective,*r.best_bound});
      out.backend=r.backend;out.backend_version=r.backend_version;
    }
    return out;
  }
  if(name=="native_binary_branching") {
    Outcome out;out.guarantee="exact";
    for(bool maximum:{false,true}) {
      O::Model m;auto x=m.add_binary(),y=m.add_binary();
      m.set_objective({{x,maximum?-2.0:2.0},{y,maximum?-1.0:1.0}},
        maximum?O::ObjectiveSense::Maximize:O::ObjectiveSense::Minimize,maximum?17:-17);
      O::NativeSearchOptions opts;opts.solve=options();opts.solve.random_seed=0;opts.solve.guarantee=O::Guarantee::Exact;
      opts.branching=O::NativeBranchingSettings{};
      const auto solved=O::solve_native_search(m,opts);const auto& r=solved.result;
      require(r.termination==O::Termination::Optimal&&r.has_solution()&&r.objective==(maximum?17:-17)&&r.best_bound==r.objective,"binary reliability optimum disagrees with enumeration");
      const auto& b=solved.branching;
      require(b.requested&&b.manual_splits>0&&b.published_pairs>0&&b.probe_status_calls>=2,"binary reliability probes/selection were bypassed");
      require(b.budget_nodes==solved.frontier.admitted_nodes+b.probe_status_calls&&b.probe_lp_calls==0,"branch probe budget/subset accounting failed");
      require(O::validate(m.snapshot(),r.values,0,0).valid,"binary reliability original witness invalid");
      out.objectives.push_back(*r.objective);out.backend=r.backend;out.backend_version=r.backend_version;
    }
    return out;
  }
  if(name=="native_complete_start") {
    Outcome out;out.guarantee="exact";
    for(bool maximum:{false,true}) {
      O::Model m;auto b=m.add_binary(),x=m.add_integer(0,4);
      const auto indicator=O::add_indicator(m,b,true,{{x,1}},3,inf);
      require(indicator.inactive_gate.has_value(),"native start fixture has no live gate");
      m.set_objective({{x,1},{b,-10}},maximum?O::ObjectiveSense::Maximize:O::ObjectiveSense::Minimize,3);
      auto opts=options();opts.backend=O::Backend::Native;opts.guarantee=O::Guarantee::Exact;opts.random_seed=0;
      opts.primal_start={{b,maximum?1.0:0.0},{x,maximum?3.0:4.0}};
      const auto r=O::solve_native(m,opts);
      double oracle=maximum?-inf:inf;
      for(int flag=0;flag<=1;++flag)for(int value=0;value<=4;++value)if(!flag||value>=3)
        oracle=maximum?std::max(oracle,value-10.0*flag+3):std::min(oracle,value-10.0*flag+3);
      require(r.termination==O::Termination::Optimal&&r.has_solution()&&r.start_submitted,"complete native start was not accepted");
      require(r.objective==oracle&&r.best_bound==oracle,"native start search failed to improve to original optimum");
      require(r.value(*indicator.inactive_gate)==1-r.value(b)&&O::validate(m.snapshot(),r.values,0,0).valid,"native start result violates original gate/model");
      out.objectives.push_back(*r.objective);out.backend=r.backend;out.backend_version=r.backend_version;
    }
    return out;
  }
  if(name=="convex_quadratic") {
    Outcome out;
    for(bool maximum:{false,true}) {
      O::QuadraticModel m;auto x=m.add_continuous(-2,3),y=m.add_continuous(-2,3);
      m.add_row({{x,1},{y,1}},1,1);
      const std::vector<O::WeightedSquare> squares={{{{x,1}},0,1,"x2"},{{{y,1}},0,1,"y2"}};
      if(maximum)m.maximize_concave_squares(squares,{},3);else m.minimize_squares(squares,{},3);
      O::QuadraticOptions opts;opts.solve=options();opts.solve.random_seed=0;
      const auto solved=O::solve_quadratic(m,opts);const auto& r=solved.result;
      require(r.termination==O::Termination::Optimal&&r.has_solution(),"quadratic solve failed: "+r.message);
      // x+y=1 => x^2+y^2 = 1/2 + 2*(x-1/2)^2, an independent exact optimum.
      near(r.value(x),0.5);near(r.value(y),0.5);near(*r.objective,maximum?2.5:3.5);
      require(solved.checks.kkt_valid&&solved.checks.bound_valid&&solved.checks.gap_upper_bound
        &&*solved.checks.gap_upper_bound>=0&&*solved.checks.gap_upper_bound<=1e-6,"quadratic original optimality checks unavailable");
      require(O::validate_quadratic(m.snapshot(),r.values).primal_valid,"quadratic original point invalid");
      out.objectives.push_back(*r.objective);out.backend=r.backend;out.backend_version=r.backend_version;
    }
    return out;
  }
  if(name=="native_root_covers") {
    Outcome out;out.guarantee="exact";
    for(bool maximum:{false,true}) {
      O::Model m;auto x=m.add_binary(),y=m.add_binary();m.add_row({{x,3},{y,3}},-inf,5);
      m.set_objective({{x,maximum?2.0:-2.0},{y,maximum?2.0:-2.0}},maximum?O::ObjectiveSense::Maximize:O::ObjectiveSense::Minimize,17);
      O::NativeLpOptions opts;opts.solve=options();opts.solve.random_seed=0;opts.solve.guarantee=O::Guarantee::Exact;
      opts.root_cover_cuts=O::NativeRootCoverSettings{};
      const auto solved=O::solve_native_lp(m,opts);const auto& r=solved.result;
      // 3(x+y)<=5 for binary x,y is exactly x+y<=1.
      require(r.termination==O::Termination::Optimal&&r.has_solution()&&r.objective==(maximum?19:15)&&r.best_bound==r.objective,"root cover solve disagrees with binary enumeration");
      const auto& root=solved.relaxation.root_cover;
      require(root.requested&&root.cuts==1&&root.nonzeros==2&&root.augmentations==1&&root.lp_calls>=1,"verified root cover preparation was bypassed");
      require(solved.relaxation.lp_calls>=root.lp_calls&&solved.relaxation.valid_bounds>=root.valid_bounds,"root LP subset accounting was lost");
      require(O::validate(m.snapshot(),r.values,0,0).valid,"root cover original witness invalid");
      out.objectives.push_back(*r.objective);out.backend=r.backend;out.backend_version=r.backend_version;
    }
    return out;
  }
  throw std::runtime_error("unknown required case: "+name);
}
}
int main(int argc,char** argv){
  const auto start=Clock::now();std::string name;
  try{
    if(argc!=9||std::string(argv[1])!="--case"||std::string(argv[3])!="--work-dir"||std::string(argv[5])!="--fixtures"||std::string(argv[7])!="--seconds")
      throw std::runtime_error("usage: optimize-fast-benchmark --case NAME --work-dir DIR --fixtures DIR --seconds SECONDS");
    name=argv[2];const double seconds=std::stod(argv[8]);require(std::isfinite(seconds)&&seconds>0&&seconds<=28,"invalid budget");
    deadline=start+std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(seconds));
    const bool native=name=="native_exact_reified"||name=="native_globals"||name=="native_regular"||name=="native_checked_lp"||name=="integer_presolve"||name=="native_frontier_bounds"||name=="native_root_covers"||name=="native_binary_branching"||name=="native_complete_start"||name=="native_neighborhoods";
    const auto backend=name=="convex_quadratic"?O::quadratic_capabilities():
      (name=="native_checked_lp"||name=="native_root_covers")?O::native_lp_capabilities():O::capabilities(native?O::Backend::Native:O::Backend::Highs);
    require(backend.available&&(name=="convex_quadratic"?backend.quadratic_programming:
      backend.mixed_integer_linear&&(native?backend.exact_solving:backend.linear_programming)),"required case backend unavailable");
    auto result=run(name,argv[4],argv[6]);require(Clock::now()<deadline,"panel deadline exceeded");
    if(result.backend.empty()){result.backend=backend.name;result.backend_version=backend.version;}
    std::cout<<std::setprecision(17)<<"{\"case\":"<<quote(name)<<",\"status\":"<<quote(result.status)<<",\"checks\":"<<checks
      <<",\"backend\":"<<quote(result.backend)<<",\"backend_version\":"<<quote(result.backend_version)
      <<",\"guarantee\":"<<quote(result.guarantee)<<",\"elapsed_seconds\":"
      <<std::chrono::duration<double>(Clock::now()-start).count()<<",\"objectives\":[";
    for(std::size_t i=0;i<result.objectives.size();++i){if(i)std::cout<<',';std::cout<<result.objectives[i];}
    std::cout<<"]}\n";return 0;
  }catch(const std::exception& e){std::cerr<<name<<": "<<e.what()<<'\n';return 1;}
}

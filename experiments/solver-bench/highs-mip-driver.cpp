// Independent reference competitor, not an enhanced Gecode component.
// This executable deliberately runs HiGHS MIP; the Gecode LP extension does not.
#include <Highs.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#include <sys/resource.h>

using I=std::int64_t;
using Clock=std::chrono::steady_clock;
constexpr double candidate_tolerance=1e-7;

static bool add(I a,I b,I& out) {
  if((b>0 && a>std::numeric_limits<I>::max()-b) ||
     (b<0 && a<std::numeric_limits<I>::min()-b))return false;
  out=a+b;return true;
}
struct Row {I rhs;std::vector<std::pair<int,I>> terms;};
struct Model {
  std::vector<I> costs;
  std::vector<Row> rows;
  std::vector<int> incumbent;
  I incumbent_cost=0;
  bool verify(const std::vector<int>& x,I& objective) const {
    if(x.size()!=costs.size())return false;
    for(int v:x)if(v!=0 && v!=1)return false;
    for(const auto& row:rows) {
      I value=0;
      for(auto [j,a]:row.terms)if(x[j] && !add(value,a,value))return false;
      if(value<row.rhs)return false;
    }
    I value=0;
    for(std::size_t j=0;j<x.size();++j)if(x[j] && !add(value,costs[j],value))return false;
    objective=value;return true;
  }
  explicit Model(const char* path) {
    std::ifstream f(path);int n,m;
    if(!(f>>n>>m) || n<=0 || n>10000 || m<0 || m>10000 || 1LL*n*m>10000000)
      throw std::runtime_error("Invalid dimensions");
    costs.resize(n);rows.resize(m);
    const auto coefficient=[](I value) {return value>=-1000000000LL && value<=1000000000LL;};
    for(auto& c:costs)if(!(f>>c) || !coefficient(c))throw std::runtime_error("Invalid objective coefficient");
    for(auto& row:rows) {
      int count;
      if(!(f>>row.rhs>>count) || !coefficient(row.rhs) || count<0 || count>n)
        throw std::runtime_error("Invalid row");
      int previous=-1;
      for(int k=0;k<count;++k) {
        int j;I a;
        if(!(f>>j>>a) || j<=previous || j>=n || !a || !coefficient(a))
          throw std::runtime_error("Invalid sparse coefficient");
        row.terms.emplace_back(j,a);previous=j;
      }
    }
    std::string trailer;int present;
    if(!(f>>trailer>>present) || trailer!="incumbent" || (present!=0 && present!=1))
      throw std::runtime_error("Invalid incumbent trailer");
    if(present) {
      incumbent.resize(n);
      for(int& v:incumbent)if(!(f>>v))throw std::runtime_error("Invalid incumbent bit");
      if(!verify(incumbent,incumbent_cost))throw std::runtime_error("Invalid original-model incumbent");
    }
    std::string extra;if(f>>extra)throw std::runtime_error("Unexpected trailing input");
  }
};

struct Observer {
  const Model& model;
  Clock::time_point begin;
  double limit_ms;
  std::vector<int> best,within;
  I cost=0,within_cost=0;
  std::vector<std::pair<double,I>> improvements;
  std::uint64_t checked=0,rejected=0;
  double elapsed() const {return std::chrono::duration<double,std::milli>(Clock::now()-begin).count();}
  bool offer(const std::vector<double>& values,I& exact_cost) {
    ++checked;
    if(values.size()!=model.costs.size()){++rejected;return false;}
    std::vector<int> point(values.size());
    for(std::size_t j=0;j<values.size();++j) {
      const double value=values[j];
      if(!std::isfinite(value)){++rejected;return false;}
      const double rounded=std::round(value);
      if((rounded!=0.0 && rounded!=1.0) || std::abs(value-rounded)>candidate_tolerance) {
        ++rejected;return false;
      }
      point[j]=static_cast<int>(rounded);
    }
    if(!model.verify(point,exact_cost)){++rejected;return false;}
    if(best.empty() || exact_cost<cost) {
      const double stamp=elapsed();best=point;cost=exact_cost;
      improvements.emplace_back(stamp,cost);
      if(stamp<=limit_ms){within=std::move(point);within_cost=cost;}
    }
    return true;
  }
};

static void require_ok(HighsStatus status,const char* operation) {
  if(status!=HighsStatus::kOk)throw std::runtime_error(std::string("HiGHS reference: ")+operation);
}
static void array(const std::vector<int>& x) {
  std::cout<<'[';for(std::size_t j=0;j<x.size();++j)std::cout<<(j?",":"")<<x[j];std::cout<<']';
}
static void number(double value) {
  if(std::isfinite(value))std::cout<<value;else std::cout<<"null";
}

int main(int argc,char** argv) {
  try {
    if(argc!=5)throw std::runtime_error("Usage: highs-mip-driver INPUT LIMIT_MS WARM_START REPEATS");
    Model model(argv[1]);const double limit=std::stod(argv[2]);
    const int warm_value=std::stoi(argv[3]),repeats=std::stoi(argv[4]);
    if(!std::isfinite(limit) || limit<=0 || limit>86400000 ||
       (warm_value!=0 && warm_value!=1) || repeats<1)throw std::runtime_error("Invalid budget/start/repeats");
    const bool warm=warm_value!=0;
    for(int rep=0;rep<repeats;++rep) {
      const auto begin=Clock::now();Observer observer{model,begin,limit};
      if(warm && !model.incumbent.empty()) {
        observer.best=observer.within=model.incumbent;
        observer.cost=observer.within_cost=model.incumbent_cost;
      }
      HighsModelStatus model_status=HighsModelStatus::kNotset;
      HighsStatus run_status=HighsStatus::kOk;
      std::int64_t nodes=0;double dual_bound=std::numeric_limits<double>::quiet_NaN();
      double reported_objective=dual_bound,gap=dual_bound,build_ms=0;
      std::string version;
      bool ran=false,final_valid=false;I final_cost=0;
      {
        Highs highs;
        version=highs.version();
        require_ok(highs.setOptionValue("output_flag",false),"output option");
        require_ok(highs.setOptionValue("threads",1),"threads option");
        require_ok(highs.setOptionValue("parallel","off"),"parallel option");
        require_ok(highs.setOptionValue("random_seed",0),"random seed");
        require_ok(highs.setOptionValue("mip_rel_gap",0.0),"relative gap");
        require_ok(highs.setOptionValue("mip_abs_gap",0.0),"absolute gap");
        require_ok(highs.setOptionValue("mip_feasibility_tolerance",candidate_tolerance),"integrality tolerance");
        HighsLp lp;lp.num_col_=static_cast<HighsInt>(model.costs.size());
        lp.num_row_=static_cast<HighsInt>(model.rows.size());lp.sense_=ObjSense::kMinimize;
        lp.col_cost_.assign(model.costs.begin(),model.costs.end());
        lp.col_lower_.assign(lp.num_col_,0.0);lp.col_upper_.assign(lp.num_col_,1.0);
        // Integrality is exclusive to this separate reference competitor.
        lp.integrality_.assign(lp.num_col_,HighsVarType::kInteger);
        lp.a_matrix_.format_=MatrixFormat::kRowwise;lp.a_matrix_.num_col_=lp.num_col_;lp.a_matrix_.num_row_=lp.num_row_;
        lp.a_matrix_.start_.assign(1,0);
        for(const auto& row:model.rows) {
          lp.row_lower_.push_back(static_cast<double>(row.rhs));lp.row_upper_.push_back(kHighsInf);
          for(auto [j,a]:row.terms){lp.a_matrix_.index_.push_back(j);lp.a_matrix_.value_.push_back(static_cast<double>(a));}
          lp.a_matrix_.start_.push_back(static_cast<HighsInt>(lp.a_matrix_.value_.size()));
        }
        require_ok(highs.passModel(std::move(lp)),"model construction");
        require_ok(highs.setCallback(HighsCallbackFunctionType([&](int type,const std::string&,
                        const HighsCallbackOutput* output,HighsCallbackInput* input,void*) {
          if(type==kCallbackMipImprovingSolution && output) {I cost;observer.offer(output->mip_solution,cost);}
          if(type==kCallbackMipInterrupt && input && observer.elapsed()>=limit)input->user_interrupt=true;
        })),"callback registration");
        require_ok(highs.startCallback(kCallbackMipImprovingSolution),"solution callback");
        require_ok(highs.startCallback(kCallbackMipInterrupt),"interrupt callback");
        if(warm && !model.incumbent.empty()) {
          HighsSolution start;start.col_value.assign(model.incumbent.begin(),model.incumbent.end());
          require_ok(highs.setSolution(start),"common start");
        }
        build_ms=observer.elapsed();const double remaining=limit-build_ms;
        if(remaining>0) {
          require_ok(highs.setOptionValue("time_limit",remaining/1000.0),"remaining wall allowance");
          ran=true;run_status=highs.run();model_status=highs.getModelStatus();
          const auto& solution=highs.getSolution();
          if(solution.value_valid)final_valid=observer.offer(solution.col_value,final_cost);
          const auto& info=highs.getInfo();
          if(info.valid){nodes=info.mip_node_count;dual_bound=info.mip_dual_bound;gap=info.mip_gap;reported_objective=info.objective_function_value;}
        }
      }
      const double elapsed=observer.elapsed();
      const bool numeric_optimal=ran && model_status==HighsModelStatus::kOptimal;
      const bool objective_agrees=final_valid && std::isfinite(reported_objective) &&
        std::abs(reported_objective-static_cast<double>(final_cost))<=1e-6;
      const bool optimal=run_status!=HighsStatus::kError && numeric_optimal && objective_agrees && final_cost==observer.cost;
      const bool infeasible=ran && model_status==HighsModelStatus::kInfeasible;
      const bool contradiction=infeasible && !observer.best.empty();
      const char* status=(run_status==HighsStatus::kError || contradiction)?"error":
        optimal?"optimal":infeasible?"infeasible":!observer.best.empty()?"feasible":"unknown";
      struct rusage usage;getrusage(RUSAGE_SELF,&usage);long rss=usage.ru_maxrss;
#ifdef __APPLE__
      rss/=1024;
#endif
      std::cout<<std::setprecision(12)<<"{\"status\":\""<<status<<"\",\"solver\":\"HiGHS\",\"version\":\""<<version
        <<"\",\"track\":\"highs_mip_reference\",\"highs_mip_used\":true,\"gecode_used\":false,\"exact_dual_certificate\":false"
        <<",\"optimality_basis\":\"HiGHS numerical MIP status; exact primal witness check only\",\"numerical_optimal\":"<<(numeric_optimal?"true":"false")
        <<",\"highs_model_status\":"<<static_cast<int>(model_status)<<",\"highs_run_status\":"<<static_cast<int>(run_status)
        <<",\"objective_agrees_with_numeric_report\":"<<(objective_agrees?"true":"false")
        <<",\"elapsed_ms\":"<<elapsed<<",\"build_ms\":"<<build_ms<<",\"nodes\":"<<nodes
        <<",\"peak_rss_kb\":"<<rss<<",\"candidate_tolerance\":"<<candidate_tolerance
        <<",\"exact_candidate_checks\":"<<observer.checked<<",\"rejected_candidates\":"<<observer.rejected
        <<",\"objective\":";
      if(observer.best.empty())std::cout<<"null";else std::cout<<observer.cost;
      std::cout<<",\"assignment\":";array(observer.best);
      std::cout<<",\"objective_at_limit\":";if(observer.within.empty())std::cout<<"null";else std::cout<<observer.within_cost;
      std::cout<<",\"assignment_at_limit\":";array(observer.within);
      std::cout<<",\"reported_objective\":";number(reported_objective);
      std::cout<<",\"reported_dual_bound\":";number(dual_bound);
      std::cout<<",\"reported_mip_gap\":";number(gap);
      std::cout<<",\"improvements\":[";
      for(std::size_t j=0;j<observer.improvements.size();++j)
        std::cout<<(j?",":"")<<'['<<observer.improvements[j].first<<','<<observer.improvements[j].second<<']';
      std::cout<<"]}\n";
    }
  } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}

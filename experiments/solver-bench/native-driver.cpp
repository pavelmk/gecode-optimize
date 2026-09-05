#include <gecode/int.hh>
#include <gecode/minimodel.hh>
#include <gecode/search.hh>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <memory>
#include <numeric>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/resource.h>
using namespace Gecode;
using Clock=std::chrono::steady_clock;

struct Instance {
  std::string family;
  int size,machines,rows,n,horizon=0,upper=0;
  std::vector<int> data,incumbent;
  int initial=0;
  explicit Instance(const char* path) {
    std::ifstream f(path);
    if (!(f>>family>>size>>machines>>rows) || size<1 || size>100 || rows<0 || rows>10000)
      throw std::runtime_error("Bad native input");
    if (family=="native_rcpsp") {
      if(machines<1 || machines>10)throw std::runtime_error("Resource dimensions");
      n=size;data.resize(machines+n*(machines+1)+2*rows);
    } else if (family=="job_shop") {
      if (machines<1 || machines>100 || rows!=size*machines) throw std::runtime_error("Job dimensions");
      n=size*machines;data.resize(2*rows);
    } else if (family=="native_coloring") {n=size;data.resize(rows*2);}
    else if (family=="native_tsp" || family=="weighted_queens") {n=size;data.resize(size*size);}
    else throw std::runtime_error("Unknown native family");
    for (int&v:data) if (!(f>>v) || v<0 || v>100000) throw std::runtime_error("Bad native data");
    incumbent.resize(n);
    for(int&v:incumbent) if(!(f>>v))throw std::runtime_error("Bad native incumbent");
    if(family=="native_rcpsp") {
      for(int r=0;r<machines;++r)if(data[r]<1)throw std::runtime_error("Resource capacity");
      for(int i=0;i<n;++i){int offset=machines+i*(machines+1);if(data[offset]<1)throw std::runtime_error("Task duration");horizon+=data[offset];for(int r=0;r<machines;++r)if(data[offset+r+1]>data[r])throw std::runtime_error("Task demand");}
      int edges=machines+n*(machines+1);for(int k=0;k<2*rows;++k)if(data[edges+k]>=n)throw std::runtime_error("Precedence index");
      for(int i=0;i<n;++i){if(incumbent[i]<0 || incumbent[i]>horizon)throw std::runtime_error("Start domain");initial=std::max(initial,incumbent[i]+data[machines+i*(machines+1)]);}
      upper=horizon;
    } else if(family=="job_shop") {
      for(int i=0;i<n;++i) {if(data[2*i]>=machines || data[2*i+1]<1)throw std::runtime_error("Job data");horizon+=data[2*i+1];}
      for(int i=0;i<n;++i) {if(incumbent[i]<0 || incumbent[i]>horizon)throw std::runtime_error("Job incumbent domain");initial=std::max(initial,incumbent[i]+data[2*i+1]);}
      upper=horizon;
    } else if(family=="native_coloring") {
      for(int v:incumbent)if(v<0 || v>=size)throw std::runtime_error("Color incumbent domain");
      upper=size;initial=*std::max_element(incumbent.begin(),incumbent.end())+1;
      for(int v:data)if(v>=size)throw std::runtime_error("Bad vertex");
    } else {
      for(int i=0;i<size;++i) {upper+=*std::max_element(data.begin()+i*size,data.begin()+(i+1)*size);if(incumbent[i]<0||incumbent[i]>=size)throw std::runtime_error("Bad assignment");initial+=data[i*size+incumbent[i]];}
    }
  }
};

class Model : public IntMinimizeSpace {
public:
  const Instance* input;
  IntVarArray x;
  IntVar objective;
  Model(const Instance& p,const std::string& branching,bool warm,
        std::optional<int> cutoff=std::nullopt,
        const std::vector<int>* fixings=nullptr,
        const std::vector<int>* preferred=nullptr)
    : input(&p),x(*this,p.n,0,(p.family=="job_shop" || p.family=="native_rcpsp")?p.horizon:p.size-1),objective(*this,0,p.upper) {
    if(p.family=="native_rcpsp") {
      IntArgs durations;IntVarArgs ends;
      for(int i=0;i<p.n;++i){int duration=p.data[p.machines+i*(p.machines+1)];durations<<duration;ends<<expr(*this,x[i]+duration);}
      for(int r=0;r<p.machines;++r){IntArgs demands;for(int i=0;i<p.n;++i)demands<<p.data[p.machines+i*(p.machines+1)+r+1];cumulative(*this,p.data[r],x,durations,demands);}
      int edges=p.machines+p.n*(p.machines+1);for(int k=0;k<p.rows;++k){int a=p.data[edges+2*k],b=p.data[edges+2*k+1];rel(*this,x[a]+durations[a]<=x[b]);}
      max(*this,ends,objective);
    } else if(p.family=="job_shop") {
      IntVarArgs ends;
      for(int j=0;j<p.size;++j) for(int k=0;k<p.machines;++k) {
        int a=j*p.machines+k;
        if(k+1<p.machines)rel(*this,x[a]+p.data[2*a+1]<=x[a+1]);
        else ends<<expr(*this,x[a]+p.data[2*a+1]);
      }
      for(int machine=0;machine<p.machines;++machine) {
        IntVarArgs starts;IntArgs durations;
        for(int a=0;a<p.n;++a)if(p.data[2*a]==machine){starts<<x[a];durations<<p.data[2*a+1];}
        unary(*this,starts,durations,IPL_DOM);
      }
      max(*this,ends,objective);
    } else if(p.family=="native_tsp") {
      IntArgs costs(p.size*p.size,p.data.data());
      IntVarArgs edge_costs(*this,p.size,0,p.upper);
      circuit(*this,costs,x,edge_costs,objective,IPL_DOM);
    } else if(p.family=="native_coloring") {
      for(int i=0;i<p.rows;++i)rel(*this,x[p.data[2*i]],IRT_NQ,x[p.data[2*i+1]]);
      IntVar highest(*this,0,p.size-1);max(*this,x,highest);rel(*this,objective==highest+1);
      // Standard first-use label symmetry breaking, identical in both binaries.
      rel(*this,x[0],IRT_EQ,0);
      for(int i=1;i<p.size;++i) {
        IntVarArgs prefix;for(int j=0;j<i;++j)prefix<<x[j];
        IntVar previous(*this,0,p.size-1);max(*this,prefix,previous);rel(*this,x[i]<=previous+1);
      }
    } else {
      distinct(*this,x,IPL_DOM);
      distinct(*this,IntArgs::create(p.size,0,1),x,IPL_DOM);
      distinct(*this,IntArgs::create(p.size,0,-1),x,IPL_DOM);
      IntVarArgs costs;
      for(int i=0;i<p.size;++i){IntArgs fees(p.size,p.data.data()+i*p.size);IntVar cost(*this,0,p.upper);element(*this,fees,x[i],cost);costs<<cost;}
      linear(*this,costs,IRT_EQ,objective);
    }
    if(warm)rel(*this,objective,IRT_LE,cutoff.value_or(p.initial));
    if(fixings) {
      if(fixings->size()!=static_cast<std::size_t>(p.n))
        throw std::runtime_error("Repair fixing dimensions");
      for(int i=0;i<p.n;++i)
        if((*fixings)[i]>=0)rel(*this,x[i],IRT_EQ,(*fixings)[i]);
    }
    IntVarBranch variables=INT_VAR_AFC_SIZE_MAX(0.99);
    if(branching=="size")variables=INT_VAR_SIZE_MIN();
    else if(branching=="degree")variables=INT_VAR_DEGREE_SIZE_MAX();
    else if(branching!="afc")throw std::runtime_error("Unknown branching");
    IntValBranch values=INT_VAL_MIN();
    if(p.family=="native_tsp" || p.family=="weighted_queens")
      values=INT_VAL([](const Space& home,IntVar v,int i){
        const auto& p=*static_cast<const Model&>(home).input;int best=v.min();
        for(IntVarValues values(v);values();++values)if(p.data[i*p.size+values.val()]<p.data[i*p.size+best])best=values.val();
        return best;
      });
    if(preferred)
      values=INT_VAL([preferred](const Space& home,IntVar v,int i){
        if(i>=0 && static_cast<std::size_t>(i)<preferred->size() &&
           v.in((*preferred)[i]))return (*preferred)[i];
        const auto& p=*static_cast<const Model&>(home).input;int best=v.min();
        if(p.family=="native_tsp" || p.family=="weighted_queens")
          for(IntVarValues values(v);values();++values)
            if(p.data[i*p.size+values.val()]<p.data[i*p.size+best])best=values.val();
        return best;
      });
    branch(*this,x,variables,values);
  }
  Model(Model& o):IntMinimizeSpace(o),input(o.input){x.update(*this,o.x);objective.update(*this,o.objective);}
  Space* copy() override{return new Model(*this);}
  IntVar cost() const override{return objective;}
};

int main(int argc,char**argv) {
  try {
    if(argc!=7)throw std::runtime_error("Usage: native-driver input native|lns|incumbent branching limit_ms warm repeats");
    Instance input(argv[1]);std::string mode=argv[2],branching=argv[3];double limit=std::stod(argv[4]);bool warm=std::stoi(argv[5])!=0;int repeats=std::stoi(argv[6]);
    if((mode!="native" && mode!="lns" && mode!="incumbent") || !std::isfinite(limit) || limit<=0 || limit>86400000 || repeats<1)throw std::runtime_error("Invalid native configuration");
    // Input validation is outside solve timing, as for binary input checking.
    { Model check(input,branching,false);
      for(int j=0;j<input.n;++j)rel(check,check.x[j],IRT_EQ,input.incumbent[j]);
      if(check.status()!=SS_SOLVED || check.objective.val()!=input.initial)
        throw std::runtime_error("Initial witness does not satisfy the native model");
    }
    for(int rep=0;rep<repeats;++rep){
      auto begin=Clock::now();Search::TimeStop stop(limit);std::vector<int> best=warm?input.incumbent:std::vector<int>{};int best_cost=warm?input.initial:0;
      std::vector<std::pair<double,int>> improvements;
      std::uint64_t heuristic_nodes=0,heuristic_failures=0,heuristic_propagations=0;
      unsigned neighborhoods=0;double heuristic_ms=0;
      // A benchmark controller using existing Gecode modeling/search primitives.
      // It is not a new core LNS capability. Repair spaces are discarded before
      // a fresh, unrestricted proof search; no neighborhood proves global optimality.
      if(mode=="lns" && !best.empty()) {
        const auto repair_begin=Clock::now();
        const auto deadline=begin+std::chrono::duration_cast<Clock::duration>(
          std::chrono::duration<double,std::milli>(std::min(100.0,limit*.15)));
        std::mt19937 random(9173);
        for(unsigned attempt=0;attempt<8 && Clock::now()<deadline;++attempt) {
          std::vector<int> fixings=best,indices(input.n);
          std::iota(indices.begin(),indices.end(),0);
          std::shuffle(indices.begin(),indices.end(),random);
          const std::size_t free=std::min(best.size(),std::max<std::size_t>(6,best.size()*(attempt%3+1)/5));
          for(std::size_t j=0;j<free;++j)fixings[indices[j]]=-1;
          const double remaining=std::chrono::duration<double,std::milli>(deadline-Clock::now()).count();
          if(remaining<=0)break;
          Search::TimeStop local_stop(std::min(15.0,remaining));
          Search::Options local_options;local_options.threads=1;local_options.stop=&local_stop;
          auto repair=std::make_unique<Model>(input,branching,true,best_cost,&fixings);
          {
            BAB<Model> engine(repair.get(),local_options);repair.reset();
            while(Model* solution=engine.next()) {
              for(int j=0;j<input.n;++j)best[j]=solution->x[j].val();
              best_cost=solution->objective.val();delete solution;
              improvements.emplace_back(std::chrono::duration<double,std::milli>(Clock::now()-begin).count(),best_cost);
            }
            const auto stats=engine.statistics();heuristic_nodes+=stats.node;
            heuristic_failures+=stats.fail;heuristic_propagations+=stats.propagate;
          }
          ++neighborhoods;
        }
        heuristic_ms=std::chrono::duration<double,std::milli>(Clock::now()-repair_begin).count();
      }
      // The preferred vector's object address remains stable until the engine
      // is destroyed. One search thread observes updates after each solution.
      const std::vector<int>* preferred=mode=="incumbent" ? &best : nullptr;
      std::unique_ptr<Model> root;
      if(mode=="native")root=std::make_unique<Model>(input,branching,warm);
      else root=std::make_unique<Model>(input,branching,!best.empty(),
                                       best.empty()?std::nullopt:std::optional<int>(best_cost),nullptr,preferred);
      auto built=Clock::now();Search::Options options;options.threads=1;options.stop=&stop;Search::Statistics stats;bool stopped;
      {BAB<Model> engine(root.get(),options);root.reset();while(Model*solution=engine.next()){best.resize(input.n);for(int j=0;j<input.n;++j)best[j]=solution->x[j].val();best_cost=solution->objective.val();delete solution;improvements.emplace_back(std::chrono::duration<double,std::milli>(Clock::now()-begin).count(),best_cost);}stats=engine.statistics();stopped=engine.stopped();}
      auto end=Clock::now();struct rusage usage;getrusage(RUSAGE_SELF,&usage);long rss=usage.ru_maxrss;
#ifdef __APPLE__
      rss/=1024;
#endif
      std::cout<<"{\"status\":\""<<(best.empty()?(stopped?"unknown":"infeasible"):(stopped?"feasible":"optimal"))<<"\",\"mode\":\""<<mode<<"\",\"branching\":\""<<branching<<"\",\"stopped\":"<<(stopped?"true":"false")<<",\"elapsed_ms\":"<<std::chrono::duration<double,std::milli>(end-begin).count()<<",\"build_ms\":"<<std::chrono::duration<double,std::milli>(built-begin).count()<<",\"pre_proof_ms\":"<<std::chrono::duration<double,std::milli>(built-begin).count()<<",\"heuristic_ms\":"<<heuristic_ms<<",\"nodes\":"<<stats.node<<",\"heuristic_nodes\":"<<heuristic_nodes<<",\"total_nodes\":"<<(stats.node+heuristic_nodes)<<",\"neighborhoods\":"<<neighborhoods<<",\"heuristic_failures\":"<<heuristic_failures<<",\"heuristic_propagations\":"<<heuristic_propagations<<",\"failures\":"<<stats.fail<<",\"propagations\":"<<stats.propagate<<",\"peak_rss_kb\":"<<rss<<",\"lp_calls\":0,\"lp_ms\":0,\"objective\":";
      if(best.empty())std::cout<<"null";else std::cout<<best_cost;
      std::cout<<",\"assignment\":[";for(std::size_t j=0;j<best.size();++j)std::cout<<(j?",":"")<<best[j];std::cout<<"],\"improvements\":[";for(std::size_t j=0;j<improvements.size();++j)std::cout<<(j?",":"")<<'['<<improvements[j].first<<','<<improvements[j].second<<']';std::cout<<"]}\n";
    }
  }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}

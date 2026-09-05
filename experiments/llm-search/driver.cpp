#include <gecode/int.hh>
#include <gecode/minimodel.hh>
#include <gecode/search.hh>
#ifdef GECODE_EXPERIMENTAL
#include <gecode/minimodel/experimental-cliques.hpp>
#endif
#include <algorithm>
#include <chrono>
#include <fstream>
#include <iostream>
#include <memory>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>
#if defined(__unix__) || defined(__APPLE__)
#include <sys/resource.h>
#endif

using namespace Gecode;
using Clock = std::chrono::steady_clock;

struct Instance {
  std::string family;
  int n, k = 0;
  std::vector<int> weights;
  std::vector<std::pair<int,int>> edges;
  explicit Instance(const char* path) {
    std::ifstream f(path);
    if (!(f >> family >> n) || n <= 0 || n > 10000)
      throw std::runtime_error("Invalid instance header");
    int e = 0;
    if (family == "coloring") f >> k >> e;
    else if (family == "scheduling") f >> k;
    else if (family == "vertex_cover") f >> e;
    else throw std::runtime_error("Unknown problem family");
    if (family != "vertex_cover" && k <= 0)
      throw std::runtime_error("Invalid machine/color count");
    if (family != "coloring") {
      weights.resize(n);
      for (int& w : weights) {
        if (!(f >> w) || w <= 0) throw std::runtime_error("Invalid weight");
      }
    }
    if (e < 0 || e > 10000000) throw std::runtime_error("Invalid edge count");
    for (int j=0; j<e; ++j) {
      int u, v;
      if (!(f >> u >> v) || u<0 || v<0 || u>=n || v>=n)
        throw std::runtime_error("Invalid edge");
      edges.emplace_back(u,v);
    }
    if (!f) throw std::runtime_error("Truncated instance");
  }
};

class Model : public IntMinimizeSpace {
public:
  IntVarArray x;
  IntVar z;
  Model(const Instance& p, bool cliques, const std::string& branching)
      : x(*this,p.n,0,p.family=="vertex_cover" ? 1 : p.k-1),
        z(*this,0,std::accumulate(p.weights.begin(),p.weights.end(),0)) {
    if (p.family == "coloring") {
      IntArgs edges(static_cast<int>(p.edges.size()*2));
      for (int j=0; j<static_cast<int>(p.edges.size()); ++j) {
        edges[2*j]=p.edges[j].first;
        edges[2*j+1]=p.edges[j].second;
      }
#ifdef GECODE_EXPERIMENTAL
      if (cliques) Experimental::rel_with_cliques(*this,x,edges,IPL_DOM);
      else
#endif
        for (auto [u,v] : p.edges) rel(*this,x[u],IRT_NQ,x[v]);
      // Color names are interchangeable; this is valid in both versions.
      rel(*this,x[0],IRT_EQ,0);
    } else if (p.family == "scheduling") {
      int total=std::accumulate(p.weights.begin(),p.weights.end(),0);
      IntVarArgs loads(*this,p.k,0,total);
      IntArgs durations(p.n);
      for (int i=0;i<p.n;++i) durations[i]=p.weights[i];
      binpacking(*this,loads,x,durations);
      max(*this,loads,z);
      rel(*this,z,IRT_GQ,std::max((total+p.k-1)/p.k,
                                *std::max_element(p.weights.begin(),p.weights.end())));
      rel(*this,x[0],IRT_EQ,0);
    } else {
      for (auto [u,v] : p.edges) rel(*this,x[u]+x[v]>=1);
      IntArgs w(p.n);
      for (int i=0;i<p.n;++i) w[i]=p.weights[i];
      linear(*this,w,x,IRT_EQ,z);
    }
    // Keep branching identical when isolating checkpointing/clique effects.
    if (branching=="afc") branch(*this,x,INT_VAR_AFC_SIZE_MAX(0.99),INT_VAL_MIN());
    else if (branching=="size") branch(*this,x,INT_VAR_SIZE_MIN(),INT_VAL_MIN());
    else if (branching=="degree") branch(*this,x,INT_VAR_DEGREE_SIZE_MAX(),INT_VAL_MIN());
    else throw std::runtime_error("Unknown branching policy");
  }
  Model(Model& s) : IntMinimizeSpace(s) { x.update(*this,s.x); z.update(*this,s.z); }
  Space* copy() override { return new Model(*this); }
  IntVar cost() const override { return z; }
};

int main(int argc,char** argv) {
  try {
    if (argc!=8) throw std::runtime_error(
      "Usage: driver INSTANCE CLIQUES CHECKPOINT_PROPAGATIONS COPY_DISTANCE BRANCHING TIME_LIMIT_MS REPEATS");
    Instance p(argv[1]);
    bool cliques=std::stoi(argv[2])!=0;
    unsigned long cp=std::stoul(argv[3]);
    unsigned int cd=std::stoul(argv[4]);
    std::string branching=argv[5];
    double limit=std::stod(argv[6]);
    int repeats=std::stoi(argv[7]);
    if (limit<=0 || repeats<=0 || cd==0) throw std::runtime_error("Invalid budget");
#ifndef GECODE_EXPERIMENTAL
    if (cp || cliques) throw std::runtime_error("Stock executable cannot enable enhancements");
#endif
    for (int repeat=0;repeat<repeats;++repeat) {
      auto start=Clock::now();
      Search::TimeStop stop(limit);
      Search::Options o;
      o.threads=1; o.stop=&stop; o.c_d=cd;
#ifdef GECODE_EXPERIMENTAL
      o.c_p=cp;
#endif
      auto root=std::make_unique<Model>(p,cliques,branching);
      auto built=Clock::now();
      std::unique_ptr<Model> best;
      Search::Statistics stats;
      bool stopped=false;
      std::vector<std::pair<double,int>> improvements;
      if (p.family=="coloring") {
        DFS<Model> engine(root.get(),o); root.reset();
        best.reset(engine.next());
        stopped=engine.stopped(); stats=engine.statistics();
      } else {
        BAB<Model> engine(root.get(),o); root.reset();
        while (Model* s=engine.next()) {
          best.reset(s);
          improvements.emplace_back(std::chrono::duration<double,std::milli>(Clock::now()-start).count(),s->z.val());
        }
        stopped=engine.stopped(); stats=engine.statistics();
      }
      auto end=Clock::now();
      long peak_rss_kb=0;
#if defined(__unix__) || defined(__APPLE__)
      struct rusage usage;
      if (getrusage(RUSAGE_SELF,&usage)==0) {
        peak_rss_kb=usage.ru_maxrss;
#ifdef __APPLE__
        peak_rss_kb/=1024;
#endif
      }
#endif
      std::string status=best ? (p.family=="coloring" || stopped ? "feasible" : "optimal")
                              : (stopped ? "unknown" : "infeasible");
      std::cout << "{\"status\":\"" << status << "\",\"family\":\"" << p.family
                << "\",\"repeat\":" << repeat << ",\"stopped\":" << (stopped?"true":"false")
                << ",\"elapsed_ms\":" << std::chrono::duration<double,std::milli>(end-start).count()
                << ",\"build_ms\":" << std::chrono::duration<double,std::milli>(built-start).count()
                << ",\"peak_rss_kb\":" << peak_rss_kb
                << ",\"nodes\":" << stats.node << ",\"failures\":" << stats.fail
                << ",\"propagations\":" << stats.propagate << ",\"depth\":" << stats.depth
                << ",\"objective\":";
      if (best) std::cout << best->z.val(); else std::cout << "null";
      std::cout << ",\"assignment\":[";
      if (best) for (int i=0;i<p.n;++i) std::cout << (i?",":"") << best->x[i].val();
      std::cout << "],\"improvements\":[";
      for (size_t i=0;i<improvements.size();++i)
        std::cout << (i?",":"") << '[' << improvements[i].first << ',' << improvements[i].second << ']';
      std::cout << "]}" << std::endl;
    }
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}

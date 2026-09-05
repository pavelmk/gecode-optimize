#include <gecode/int.hh>
#include <gecode/search.hh>
#include <gecode/minimodel/experimental-cliques.hpp>

#include <iostream>
#include <memory>
#include <set>
#include <stdexcept>
#include <vector>

using namespace Gecode;
using Solutions = std::set<std::vector<int> >;

static void require(bool ok, const char* message) {
  if (!ok) throw std::runtime_error(message);
}

static IntArgs args(const std::vector<int>& input) {
  IntArgs result(static_cast<int>(input.size()));
  for (int i=0; i<result.size(); i++) result[i] = input[i];
  return result;
}

class Graph : public Space {
public:
  IntVarArray x;
  unsigned int cliques;
  Graph(int n, int colors, const std::vector<int>& edges, bool strengthen,
        bool hall=false)
    : x(*this,n,0,colors-1), cliques(0) {
    if (hall) {
      dom(*this,x[0],0,1);
      dom(*this,x[1],0,1);
    }
    if (strengthen)
      cliques = Experimental::rel_with_cliques(*this,x,args(edges));
    else
      for (std::size_t i=0; i<edges.size(); i+=2)
        rel(*this,x[edges[i]],IRT_NQ,x[edges[i+1]]);
    branch(*this,x,INT_VAR_NONE(),INT_VAL_MIN());
  }
  Graph(Graph& other) : Space(other), cliques(other.cliques) {
    x.update(*this,other.x);
  }
  Space* copy(void) override { return new Graph(*this); }
};

static Solutions solve(int n, int colors, const std::vector<int>& edges,
                       bool strengthen) {
  Graph root(n,colors,edges,strengthen);
  DFS<Graph> search(&root);
  Solutions found;
  while (Graph* raw = search.next()) {
    std::unique_ptr<Graph> solution(raw);
    std::vector<int> values;
    for (int i=0; i<n; i++) values.push_back(solution->x[i].val());
    found.insert(values);
  }
  return found;
}

static Solutions brute(int n, int colors, const std::vector<int>& edges) {
  std::size_t assignments = 1;
  for (int i=0; i<n; i++) assignments *= colors;
  Solutions found;
  for (std::size_t id=0; id<assignments; id++) {
    std::size_t value = id;
    std::vector<int> tuple(n);
    for (int i=0; i<n; i++) { tuple[i] = value % colors; value /= colors; }
    bool valid = true;
    for (std::size_t i=0; i<edges.size(); i+=2)
      if (tuple[edges[i]] == tuple[edges[i+1]]) { valid = false; break; }
    if (valid) found.insert(tuple);
  }
  return found;
}

int main(void) {
  try {
    unsigned int cases = 0;
    // Every labelled simple graph on zero through five vertices, with one
    // through three colors. Compare both solvers with independent enumeration.
    for (int n=0; n<=5; n++) {
      std::vector<int> complete;
      for (int u=0; u<n; u++) for (int v=u+1; v<n; v++) {
        complete.push_back(u); complete.push_back(v);
      }
      const unsigned int graphs = 1u << (complete.size()/2);
      for (unsigned int mask=0; mask<graphs; mask++) {
        std::vector<int> edges;
        for (unsigned int e=0; e<complete.size()/2; e++)
          if (mask & (1u << e)) {
            edges.push_back(complete[2*e]);
            edges.push_back(complete[2*e+1]);
          }
        for (int colors=1; colors<=3; colors++) {
          const Solutions expected = brute(n,colors,edges);
          require(solve(n,colors,edges,false) == expected,"plain enumeration");
          require(solve(n,colors,edges,true) == expected,"clique enumeration");
          cases++;
        }
      }
    }
    const std::vector<int> triangle = {0,1,1,2,0,2};
    const std::vector<int> duplicates = {0,1,1,0,1,2,0,2,0,2};
    require(solve(3,3,duplicates,true) == brute(3,3,duplicates),"duplicates");
    require(solve(3,3,{0,1,2,2},true).empty(),"self loop");
    Graph duplicate_count(3,3,duplicates,true);
    require(duplicate_count.cliques == 1,"deduplicate identical cliques");

    Graph plain(3,3,triangle,false,true), strong(3,3,triangle,true,true);
    require(plain.status() == SS_BRANCH,"plain Hall status");
    require(strong.status() == SS_BRANCH,"strong Hall status");
    require(plain.x[2].size() == 3,"binary constraints leave Hall domain");
    require(strong.x[2].assigned() && strong.x[2].val() == 2,
            "distinct must remove Hall set values");

    Graph healthy(3,3,{},false);
    bool odd=false, negative=false, high=false;
    try { Experimental::rel_with_cliques(healthy,healthy.x,args({0})); }
    catch (const Int::ArgumentSizeMismatch&) { odd=true; }
    try { Experimental::rel_with_cliques(healthy,healthy.x,args({0,-1})); }
    catch (const Int::OutOfLimits&) { negative=true; }
    try { Experimental::rel_with_cliques(healthy,healthy.x,args({0,3})); }
    catch (const Int::OutOfLimits&) { high=true; }
    require(odd && negative && high,"input validation");
    require(!healthy.failed(),"invalid inputs do not mutate model");
    healthy.fail();
    require(Experimental::rel_with_cliques(healthy,healthy.x,args({0})) == 0,
            "failed-home no-op");
    std::cout << "PASS: " << cases
              << " exhaustive graph/color cases; duplicates, self loop, Hall"
                 " propagation, invalid endpoints, failed home.\n";
  } catch (const std::exception& error) {
    std::cerr << "FAIL: " << error.what() << '\n';
    return 1;
  }
}

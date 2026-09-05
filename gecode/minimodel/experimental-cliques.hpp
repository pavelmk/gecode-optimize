/*
 * Experimental, opt-in disequality-graph strengthening.
 * SPDX-License-Identifier: MIT
 */

#ifndef GECODE_MINIMODEL_EXPERIMENTAL_CLIQUES_HPP
#define GECODE_MINIMODEL_EXPERIMENTAL_CLIQUES_HPP

#include <gecode/int.hh>

#include <algorithm>
#include <set>
#include <vector>

namespace Gecode { namespace Experimental {

  /**
   * Post x[u] != x[v] for each consecutive pair of endpoint indices, then
   * add redundant distinct constraints for greedily discovered cliques.
   *
   * A clique's pairwise disequalities imply precisely the posted distinct
   * relation. Domain-consistent distinct propagation can nevertheless prune
   * more than the separate binary propagators (for example, Hall sets).
   * The existing Gecode distinct propagator performs that propagation.
   *
   * There is one greedy construction per vertex; this does not enumerate
   * all maximal cliques. Duplicate edges and duplicate cliques are removed.
   * Graph storage is O(n+m), aside from storage for at most n cliques.
   * Preprocessing is polynomial, but can still be costly on large graphs.
   * Returns the number of distinct constraints posted (possibly before a
   * failure). All supplied pairwise constraints remain part of the model.
   *
   * Odd endpoint-array lengths throw Int::ArgumentSizeMismatch; out-of-range
   * endpoints throw Int::OutOfLimits. A self edge makes the space fail.
   * Like a posting operation, an already failed home is left unchanged.
   */
  inline unsigned int
  rel_with_cliques(Home home, const IntVarArgs& x,
                   const IntArgs& endpoint_pairs,
                   IntPropLevel ipl=IPL_DOM) {
    if (home.failed())
      return 0;
    const char* location = "Experimental::rel_with_cliques";
    if (endpoint_pairs.size() % 2 != 0)
      throw Int::ArgumentSizeMismatch(location);
    const int n = x.size();
    for (int i=0; i<endpoint_pairs.size(); i++)
      if ((endpoint_pairs[i] < 0) || (endpoint_pairs[i] >= n))
        throw Int::OutOfLimits(location);

    std::vector<std::vector<int> > adjacency(n);
    for (int i=0; i<endpoint_pairs.size(); i+=2) {
      const int u = endpoint_pairs[i], v = endpoint_pairs[i+1];
      if (u == v) {
        home.fail();
        return 0;
      }
      adjacency[u].push_back(v);
      adjacency[v].push_back(u);
    }
    for (int u=0; u<n; u++) {
      std::vector<int>& neighbors = adjacency[u];
      std::sort(neighbors.begin(),neighbors.end());
      neighbors.erase(std::unique(neighbors.begin(),neighbors.end()),
                      neighbors.end());
      for (int v : neighbors)
        if (u < v) {
          rel(home,x[u],IRT_NQ,x[v]);
          if (home.failed())
            return 0;
        }
    }

    unsigned int posted = 0;
    std::set<std::vector<int> > seen;
    for (int seed=0; seed<n; seed++) {
      if (adjacency[seed].size() < 2)
        continue;
      std::vector<int> clique(1,seed);
      std::vector<int> candidates = adjacency[seed];
      while (!candidates.empty()) {
        // Highest graph degree first, with deterministic index tie-breaking.
        int chosen = candidates.front();
        for (int v : candidates)
          if (adjacency[v].size() > adjacency[chosen].size())
            chosen = v;
        clique.push_back(chosen);
        const std::vector<int>& neighbors = adjacency[chosen];
        candidates.erase(
          std::remove_if(candidates.begin(),candidates.end(),
            [&](int v) {
              return !std::binary_search(neighbors.begin(),neighbors.end(),v);
            }),candidates.end());
      }
      if (clique.size() < 3)
        continue;
      std::sort(clique.begin(),clique.end());
      if (!seen.insert(clique).second)
        continue;
      IntVarArgs members(static_cast<int>(clique.size()));
      for (int i=0; i<members.size(); i++)
        members[i] = x[clique[i]];
      distinct(home,members,ipl);
      posted++;
      if (home.failed())
        return posted;
    }
    return posted;
  }

}}

#endif

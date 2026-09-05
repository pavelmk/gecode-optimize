#include <gecode/minimodel/lp-backend.hpp>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <thread>

using namespace Gecode::Experimental::LpRelaxation;

static void check(bool ok, const char* message) {
  if (!ok) throw std::runtime_error(message);
}

int main() {
  // Fractional triangle-cover optimum is 1.5, hence integer lower bound 2.
  Backend triangle({{1,1,0, 0,1,1, 1,0,1}, {1,1,1}, {1,1,1}});
  auto t = triangle.bound({0,0,0},{1,1,1});
  check(t.valid && t.lower_bound == 2, "triangle bound");
  check(std::abs(t.lp_objective-1.5) < 1e-8, "row-dual sign/LP objective");
  // Force one sibling to a high bound, then loosen it on another sibling.
  Backend sibling({{1,1}, {1}, {2,9}});
  auto a = sibling.bound({0,1},{0,1});
  auto b = sibling.bound({1,0},{1,0});
  auto c = sibling.bound({0,0},{1,1});
  check(a.valid && a.lower_bound == 9, "first sibling");
  check(b.valid && b.lower_bound == 2, "second sibling");
  check(c.valid && c.lower_bound == 2, "restored bounds");
  // An infeasibility status is only a statistic. HiGHS may still supply
  // multipliers, in which case only the exact checker can accept a bound.
  (void) sibling.bound({0,0},{0,0});
  auto recovered = sibling.bound({0,0},{1,1});
  check(recovered.valid && recovered.lower_bound == 2, "recovery after infeasibility");
  check(sibling.statistics().infeasible_status >= 1, "infeasibility statistics");
  check(!sibling.bound({-1,0},{1,1}).valid, "nonbinary rejection");
  check(!sibling.bound({0},{1}).valid, "dimension rejection");
  bool threw = false;
  try { Backend bad({{1}, {1}, {1,2}}); } catch (const std::invalid_argument&) { threw=true; }
  check(threw,"invalid dense model rejection");
  Backend empty({{}, {}, {}});
  check(empty.bound({},{}).valid,"empty model");
  Backend box({{}, {}, {-3,4}});
  check(box.bound({0,0},{1,1}).lower_bound == -3,"negative-cost empty-row box");
  // One shared backend is serialized across callers; every bound restored.
  bool first_ok = true, second_ok = true;
  std::thread first([&] { for(int i=0;i<20;++i) { auto r=sibling.bound({0,1},{0,1}); first_ok &= r.valid && r.lower_bound==9; } });
  std::thread second([&] { for(int i=0;i<20;++i) { auto r=sibling.bound({1,0},{1,0}); second_ok &= r.valid && r.lower_bound==2; } });
  first.join(); second.join();
  check(first_ok && second_ok,"serialized concurrent sibling calls");
  const auto stats=sibling.statistics();
  check(stats.lp_calls==45 && stats.valid_bounds+stats.rejected==47 && stats.rejected>=2,"statistics");
  std::cout << "{\"status\":\"passed\",\"highs_version\":\"" << highsVersion()
            << "\",\"checks\":14,\"serialized_thread_calls\":40,"
            << "\"cases\":[\"triangle_dual_sign_and_exact_bound\","
            << "\"sibling_bound_restoration\",\"recovery_after_infeasible_lp\","
            << "\"binary_and_dimension_checks\",\"empty_models\","
            << "\"serialized_callers\"],\"lp_calls\":" << stats.lp_calls
            << ",\"valid_bounds\":" << stats.valid_bounds
            << ",\"rejected\":" << stats.rejected << "}\n";
}

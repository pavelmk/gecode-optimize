// Generated from development data only. See policy.json.
#ifndef SOLVER_BENCH_POLICY_HPP
#define SOLVER_BENCH_POLICY_HPP
#include <vector>
inline const char* select_policy(const std::vector<double>& f) {
  if(f[5] <= 0.97499999999999998) {
    if(f[8] <= 0.30410447761194026) {
      return "fix4";
    } else {
      return "native";
    }
  } else {
    if(f[0] <= 124) {
      if(f[0] <= 60) {
        return "fix8";
      } else {
        return "lns-fix4";
      }
    } else {
      return "pump-fix4";
    }
  }
}
#endif

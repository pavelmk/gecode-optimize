/* Experimental binary linear models. SPDX-License-Identifier: MIT */
#ifndef GECODE_MINIMODEL_LP_MODEL_HPP
#define GECODE_MINIMODEL_LP_MODEL_HPP

#include <gecode/int.hh>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>

namespace Gecode { namespace Experimental { namespace LpRelaxation {

/// Binary minimization: min c*x, subject to a*x >= b. Dense row-major a.
struct LinearModel {
  std::vector<std::int64_t> a, b, c;
};

inline void validate_model(const LinearModel& model) {
  const auto n=model.c.size(), m=model.b.size();
  if (n>static_cast<std::size_t>(std::numeric_limits<int>::max()) ||
      m>static_cast<std::size_t>(std::numeric_limits<int>::max()) ||
      (n && m>std::numeric_limits<std::size_t>::max()/n) || model.a.size()!=m*n)
    throw std::invalid_argument("Binary linear model dimensions");
  for (const auto* values : {&model.a,&model.b,&model.c})
    for (auto value : *values)
      if (value < -1000000000LL || value > 1000000000LL)
        throw std::invalid_argument("Binary linear coefficients must have magnitude <= 1e9");
  std::int64_t lo=0,hi=0;
  for (auto value : model.c) { if (value<0) lo+=value; else hi+=value; }
  if (lo<Int::Limits::min || hi>Int::Limits::max)
    throw std::invalid_argument("Binary objective range exceeds Gecode integer limits");
}

/// Post the original constraints. Identical code is used by both benchmarks.
inline void post_native(Home home,const IntVarArgs& x,IntVar objective,
                        const LinearModel& model) {
  validate_model(model);
  if (model.c.size()!=static_cast<std::size_t>(x.size()))
    throw Int::ArgumentSizeMismatch("LpRelaxation::post_native");
  if (home.failed()) return;
  dom(home,x,0,1);
  for (std::size_t i=0;i<model.b.size();++i) {
    IntArgs coefficients;
    IntVarArgs variables;
    for (int j=0;j<x.size();++j)
      if (model.a[i*x.size()+j]) {
        coefficients << static_cast<int>(model.a[i*x.size()+j]);
        variables << x[j];
      }
    linear(home,coefficients,variables,IRT_GQ,static_cast<int>(model.b[i]),IPL_BND);
  }
  IntArgs costs(x.size());
  for (int j=0;j<x.size();++j) costs[j]=static_cast<int>(model.c[j]);
  linear(home,costs,x,IRT_EQ,objective,IPL_BND);
}

}}}
#endif

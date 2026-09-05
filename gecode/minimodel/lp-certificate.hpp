/* Certified lower bounds for binary linear minimization.
 *
 * Experimental, opt-in support for LP-guided Gecode propagation.
 */

#ifndef __GECODE_MINIMODEL_LP_CERTIFICATE_HPP__
#define __GECODE_MINIMODEL_LP_CERTIFICATE_HPP__

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <utility>
#include <vector>

namespace Gecode { namespace Experimental { namespace LpCertificate {

  /// Denominator used for the nonnegative rational multipliers.
  constexpr std::int64_t scale = 1048576; // 2^20

#if defined(__SIZEOF_INT128__) && (defined(__GNUC__) || defined(__clang__))
  constexpr bool supported = true;
#else
  constexpr bool supported = false;
#endif

  /**
   * Convert finite candidate multipliers to nonnegative rationals q/scale.
   *
   * Negative multipliers are clipped to zero. Every resulting q is valid
   * for the certificate, even if the LP solver's multiplier was inaccurate.
   * No proximity to an optimal dual solution is assumed. On failure, the
   * output vector is unchanged.
   */
  inline bool
  quantize(const std::vector<double>& duals,
           std::vector<std::int64_t>& result) {
    std::vector<std::int64_t> candidate;
    candidate.reserve(duals.size());
    for (double dual : duals) {
      if (!std::isfinite(dual))
        return false;
      if (dual <= 0.0) {
        candidate.push_back(0);
        continue;
      }
      const double scaled = std::ldexp(dual,20);
      // Comparing against 2^63 avoids rounding INT64_MAX up to 2^63.
      if (!std::isfinite(scaled) || (scaled >= std::ldexp(1.0,63)))
        return false;
      candidate.push_back(static_cast<std::int64_t>(std::floor(scaled)));
    }
    result.swap(candidate);
    return true;
  }

  /**
   * An exact affine lower bound valid for every binary box of one model.
   *
   * Its constant is q*b and its residual coefficients are scale*c-A^T*q.
   * A prepared certificate is independent of the box used to obtain its
   * candidate LP multipliers, so descendants and siblings may evaluate it
   * safely with their own bounds. No floating-point reduced cost is used.
   */
  class Certificate {
#if defined(__SIZEOF_INT128__) && (defined(__GNUC__) || defined(__clang__))
    using Wide = __int128;
    Wide constant_ = 0;
    std::vector<Wide> residual_;
    bool valid_ = false;

    bool numerator(const std::vector<std::int64_t>& lower,
                   const std::vector<std::int64_t>& upper,
                   Wide& out) const {
      if (!valid_ || lower.size()!=residual_.size() ||
          upper.size()!=residual_.size())
        return false;
      Wide value=constant_;
      for (std::size_t j=0; j<residual_.size(); ++j) {
        if (lower[j]<0 || upper[j]>1 || lower[j]>upper[j])
          return false;
        const std::int64_t endpoint=residual_[j]>=0 ? lower[j] : upper[j];
        Wide term;
        if (__builtin_mul_overflow(residual_[j],static_cast<Wide>(endpoint),&term) ||
            __builtin_add_overflow(value,term,&value))
          return false;
      }
      out=value;
      return true;
    }

    static bool ceiling(Wide numerator, std::int64_t& out) {
      Wide value=numerator/static_cast<Wide>(scale);
      if (numerator % static_cast<Wide>(scale)>0)
        if (__builtin_add_overflow(value,static_cast<Wide>(1),&value))
          return false;
      if (value<static_cast<Wide>(std::numeric_limits<std::int64_t>::min()) ||
          value>static_cast<Wide>(std::numeric_limits<std::int64_t>::max()))
        return false;
      out=static_cast<std::int64_t>(value);
      return true;
    }
#endif
    friend bool prepare(const std::vector<std::int64_t>&,
                        const std::vector<std::int64_t>&,
                        const std::vector<std::int64_t>&,
                        const std::vector<double>&, Certificate&);

  public:
    /// Evaluate the ordinary integer lower bound; failure leaves out intact.
    bool lower_bound(const std::vector<std::int64_t>& lower,
                     const std::vector<std::int64_t>& upper,
                     std::int64_t& out) const {
#if defined(__SIZEOF_INT128__) && (defined(__GNUC__) || defined(__clang__))
      Wide value;
      return numerator(lower,upper,value) && ceiling(value,out);
#else
      (void) lower; (void) upper; (void) out;
      return false;
#endif
    }

    /**
     * Evaluate the bound and both conditional bounds for each unfixed bit.
     *
     * forbidden[j]&1 proves x[j]=0 cannot have cost<=objective_upper;
     * forbidden[j]&2 proves the same for x[j]=1. Assigned variables have
     * mask zero. All arithmetic, including the conditional difference, is
     * checked. Failure leaves both outputs unchanged.
     */
    bool filter(const std::vector<std::int64_t>& lower,
                const std::vector<std::int64_t>& upper,
                std::int64_t objective_upper, std::int64_t& bound,
                std::vector<unsigned char>& forbidden) const {
#if defined(__SIZEOF_INT128__) && (defined(__GNUC__) || defined(__clang__))
      Wide base,threshold;
      std::int64_t rounded;
      if (!numerator(lower,upper,base) || !ceiling(base,rounded) ||
          __builtin_mul_overflow(static_cast<Wide>(scale),
                                 static_cast<Wide>(objective_upper),&threshold))
        return false;
      std::vector<unsigned char> candidate(residual_.size(),0);
      for (std::size_t j=0; j<residual_.size(); ++j) {
        if (lower[j]==upper[j])
          continue;
        // An unfixed binary variable has [0,1]. Remove its contribution
        // from the box minimum, then substitute each candidate value.
        const Wide minimum=residual_[j]<0 ? residual_[j] : 0;
        Wide without;
        if (__builtin_sub_overflow(base,minimum,&without))
          return false;
        if (without>threshold)
          candidate[j]|=1;
        Wide with_one;
        if (__builtin_add_overflow(without,residual_[j],&with_one))
          return false;
        if (with_one>threshold)
          candidate[j]|=2;
      }
      bound=rounded;
      forbidden.swap(candidate);
      return true;
#else
      (void) lower; (void) upper; (void) objective_upper;
      (void) bound; (void) forbidden;
      return false;
#endif
    }
  };

  /// Prepare immutable residual data. Failure leaves out unchanged.
  inline bool
  prepare(const std::vector<std::int64_t>& A,
          const std::vector<std::int64_t>& b,
          const std::vector<std::int64_t>& c,
          const std::vector<double>& duals, Certificate& out) {
#if defined(__SIZEOF_INT128__) && (defined(__GNUC__) || defined(__clang__))
    using Wide = __int128;
    const std::size_t rows=b.size(),columns=c.size();
    if (duals.size()!=rows ||
        (rows && columns>std::numeric_limits<std::size_t>::max()/rows) ||
        A.size()!=rows*columns)
      return false;
    std::vector<std::int64_t> q;
    if (!quantize(duals,q))
      return false;
    Certificate candidate;
    candidate.residual_.resize(columns);
    for (std::size_t j=0; j<columns; ++j)
      if (__builtin_mul_overflow(static_cast<Wide>(scale),static_cast<Wide>(c[j]),
                                 &candidate.residual_[j]))
        return false;
    for (std::size_t i=0; i<rows; ++i) {
      if (!q[i])
        continue;
      Wide product;
      if (__builtin_mul_overflow(static_cast<Wide>(q[i]),static_cast<Wide>(b[i]),&product) ||
          __builtin_add_overflow(candidate.constant_,product,&candidate.constant_))
        return false;
      for (std::size_t j=0; j<columns; ++j)
        if (__builtin_mul_overflow(static_cast<Wide>(q[i]),
                                   static_cast<Wide>(A[i*columns+j]),&product) ||
            __builtin_sub_overflow(candidate.residual_[j],product,&candidate.residual_[j]))
          return false;
    }
    candidate.valid_=true;
    out=std::move(candidate);
    return true;
#else
    (void) A; (void) b; (void) c; (void) duals; (void) out;
    return false;
#endif
  }

  /**
   * Certify an integer lower bound for min c*x, Ax>=b, lower<=x<=upper.
   *
   * A is row-major with b.size() rows and c.size() columns. Bounds must
   * describe a nonempty binary box: 0<=lower[j]<=upper[j]<=1.
   * Rows and objective have exact integer coefficients.
   *
   * For any nonnegative rational y=q/scale, feasibility implies
   *
   *   c*x >= y*b + sum_j min((c-A^T*y)[j]*lower[j],
   *                          (c-A^T*y)[j]*upper[j]).
   *
   * We compute this expression with checked signed 128-bit integer
   * arithmetic and round its value upward, since c*x is integral.
   * No floating-point objective or numerical feasibility tolerance enters
   * the certificate. A true return does not assert that the model itself
   * is feasible. False means no bound was produced, and leaves out intact.
   * Compilers without the required checked arithmetic safely return false.
   */
  inline bool
  lower_bound(const std::vector<std::int64_t>& A,
              const std::vector<std::int64_t>& b,
              const std::vector<std::int64_t>& c,
              const std::vector<std::int64_t>& lower,
              const std::vector<std::int64_t>& upper,
              const std::vector<double>& duals,
              std::int64_t& out) {
#if defined(__SIZEOF_INT128__) && (defined(__GNUC__) || defined(__clang__))
    using Wide = __int128;
    const std::size_t rows = b.size();
    const std::size_t columns = c.size();
    if ((lower.size() != columns) || (upper.size() != columns) ||
        (duals.size() != rows))
      return false;
    if ((rows != 0) &&
        (columns > std::numeric_limits<std::size_t>::max()/rows))
      return false;
    if (A.size() != rows*columns)
      return false;
    for (std::size_t j=0; j<columns; ++j)
      if ((lower[j] < 0) || (upper[j] > 1) ||
          (lower[j] > upper[j]))
        return false;

    std::vector<std::int64_t> q;
    if (!quantize(duals,q))
      return false;
    std::vector<Wide> reduced(columns);
    for (std::size_t j=0; j<columns; ++j)
      if (__builtin_mul_overflow(static_cast<Wide>(scale),
                                 static_cast<Wide>(c[j]), &reduced[j]))
        return false;

    Wide numerator = 0;
    for (std::size_t i=0; i<rows; ++i) {
      if (q[i] == 0)
        continue;
      Wide product;
      if (__builtin_mul_overflow(static_cast<Wide>(q[i]),
                                 static_cast<Wide>(b[i]), &product) ||
          __builtin_add_overflow(numerator,product,&numerator))
        return false;
      for (std::size_t j=0; j<columns; ++j) {
        if (__builtin_mul_overflow(static_cast<Wide>(q[i]),
                                   static_cast<Wide>(A[i*columns+j]),
                                   &product) ||
            __builtin_sub_overflow(reduced[j],product,&reduced[j]))
          return false;
      }
    }
    for (std::size_t j=0; j<columns; ++j) {
      Wide term;
      const std::int64_t endpoint =
        reduced[j] >= 0 ? lower[j] : upper[j];
      if (__builtin_mul_overflow(reduced[j],static_cast<Wide>(endpoint),
                                 &term) ||
          __builtin_add_overflow(numerator,term,&numerator))
        return false;
    }

    // C++ division truncates toward zero. Only a positive remainder needs
    // an increment to obtain the mathematical ceiling, including for N<0.
    Wide rounded = numerator/static_cast<Wide>(scale);
    if (numerator % static_cast<Wide>(scale) > 0)
      if (__builtin_add_overflow(rounded,static_cast<Wide>(1),&rounded))
        return false;
    if ((rounded < static_cast<Wide>(std::numeric_limits<std::int64_t>::min())) ||
        (rounded > static_cast<Wide>(std::numeric_limits<std::int64_t>::max())))
      return false;
    out = static_cast<std::int64_t>(rounded);
    return true;
#else
    (void) A; (void) b; (void) c; (void) lower; (void) upper;
    (void) duals; (void) out;
    return false;
#endif
  }

}}}

#endif

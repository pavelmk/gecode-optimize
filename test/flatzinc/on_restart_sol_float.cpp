/* -*- mode: C++; c-basic-offset: 2; indent-tabs-mode: nil -*- */
/*
 *  Main authors:
 *     Jip J. Dekker <jip.dekker@monash.edu>
 *
 *  Copyright:
 *     Jip J. Dekker, 2023
 *
 *  This file is part of Gecode, the generic constraint
 *  development environment:
 *     http://www.gecode.dev
 *
 *  Permission is hereby granted, free of charge, to any person obtaining
 *  a copy of this software and associated documentation files (the
 *  "Software"), to deal in the Software without restriction, including
 *  without limitation the rights to use, copy, modify, merge, publish,
 *  distribute, sublicense, and/or sell copies of the Software, and to
 *  permit persons to whom the Software is furnished to do so, subject to
 *  the following conditions:
 *
 *  The above copyright notice and this permission notice shall be
 *  included in all copies or substantial portions of the Software.
 *
 *  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 *  EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 *  MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 *  NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
 *  LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
 *  OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
 *  WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 *
 */

#include "test/flatzinc.hh"

#include <cmath>
#include <locale>
#include <sstream>

namespace Test { namespace FlatZinc {

  namespace {
    const std::string first_y_prefix = "x = 1;\ny = ";
    const std::string remembered_suffix =
      ";\n----------\nx = 2;\ny = 1.0;\n----------\n"
      "x = 3;\ny = 2.0;\n----------\n==========\n";

    bool restart_float_output(const std::string& output) {
      // At the first solution, status=1 allows the bool_clause to hold
      // without y equalling the remembered value: y has no declared bounds.
      // Later status=4 forces that equality, so all subsequent output stays
      // exact, including the remembered values, solution order and markers.
      if (output.compare(0,first_y_prefix.size(),first_y_prefix) != 0)
        return false;
      const std::size_t end = output.find(";\n",first_y_prefix.size());
      if ((end == std::string::npos) ||
          (output.compare(end,std::string::npos,remembered_suffix) != 0))
        return false;
      const std::string spelling = output.substr(first_y_prefix.size(),
                                                 end-first_y_prefix.size());
      // Restrict the stream parser to decimal/scientific output spelling;
      // implementations can otherwise also accept hexadecimal numbers.
      if (spelling.find_first_not_of("0123456789+-.eE") != std::string::npos)
        return false;
      std::istringstream token(spelling);
      token.imbue(std::locale::classic());
      double value = 0;
      token >> std::noskipws >> value;
      return !token.fail() && token.eof() && std::isfinite(value);
    }

    /// Exercise the checker independently of the solver's chosen first y.
    class OutputCheckTest : public Base {
    public:
      OutputCheckTest(void)
        : Base("FlatZinc::on_restart::sol_float::OutputCheck") {}
      virtual bool run(void) {
        const char* accepted[] = {
          "1.0", "-1.79769313486231e+308", "0", "+0.0", "-.125",
          "1e+3", "1.7976931348623157e+308"
        };
        for (const char* token : accepted)
          if (!restart_float_output(first_y_prefix+token+remembered_suffix))
            return false;
        const char* rejected[] = {
          "", " ", "nan", "-nan", "NaN", "inf", "+inf", "-infinity",
          "1e309", "-1e309", "1 2", "1.0junk", "1.0 ", " 1.0",
          "0x1p0", "1e", "--1", "1;\n", "1\n2"
        };
        for (const char* token : rejected)
          if (restart_float_output(first_y_prefix+token+remembered_suffix))
            return false;
        const std::string good = first_y_prefix+"1.0"+remembered_suffix;
        const char* originals[] = {
          "x = 1", "x = 2", "x = 3", "y = 1.0;\n----------\nx = 3",
          "y = 2.0", "----------", "=========="
        };
        const char* replacements[] = {
          "x = 2", "x = 3", "x = 2", "y = 2.0;\n----------\nx = 3",
          "y = 1.0", "---------", "=====UNKNOWN====="
        };
        for (std::size_t i=0; i<sizeof(originals)/sizeof(*originals); ++i) {
          std::string changed = good;
          const std::size_t pos = changed.find(originals[i]);
          if (pos == std::string::npos)
            return false;
          changed.replace(pos,std::string(originals[i]).size(),replacements[i]);
          if (restart_float_output(changed))
            return false;
        }
        // Reject truncation, extra assignments/text and leading whitespace.
        for (std::size_t i=0; i<good.size(); ++i)
          if (restart_float_output(good.substr(0,i)))
            return false;
        return !restart_float_output(good+"x = 4;\n") &&
          !restart_float_output(good+"junk") &&
          !restart_float_output("\n"+good);
      }
    };

    OutputCheckTest output_check_test;

    /// Helper class to create and register tests
    class Create {
    public:

      /// Perform creation and registration
      Create(void) {
        (void) new FlatZincTest("on_restart::sol_float",
R"FZN(predicate gecode_on_restart_sol_float(var float: input,var float: out);
predicate gecode_on_restart_status(var int: s);
predicate int_eq_imp(var int: a,var int: b,var bool: r);
var 1..3: x:: output_var;
var float: y:: output_var;
var 1.0..3.0: X_INTRODUCED_2_ ::var_is_introduced :: is_defined_var;
var 1.0..3.0: X_INTRODUCED_3_ ::var_is_introduced ;
var bool: X_INTRODUCED_4_ ::var_is_introduced :: is_defined_var;
var 1..5: X_INTRODUCED_5_ ::var_is_introduced ;
var bool: X_INTRODUCED_6_ ::var_is_introduced :: is_defined_var;
array [1..1] of var int: X_INTRODUCED_1_ ::var_is_introduced  = [x];
constraint gecode_on_restart_sol_float(X_INTRODUCED_2_,X_INTRODUCED_3_);
constraint gecode_on_restart_status(X_INTRODUCED_5_);
constraint bool_clause([X_INTRODUCED_4_,X_INTRODUCED_6_],[]);
constraint int2float(x,X_INTRODUCED_2_):: defines_var(X_INTRODUCED_2_);
constraint float_eq_reif(y,X_INTRODUCED_3_,X_INTRODUCED_4_):: defines_var(X_INTRODUCED_4_);
constraint int_eq_imp(X_INTRODUCED_5_,1,X_INTRODUCED_6_):: defines_var(X_INTRODUCED_6_);
solve :: int_search(X_INTRODUCED_1_,input_order,indomain_min,complete) maximize x;
)FZN",
R"OUT(x = 1;
y = 1.0;
----------
x = 2;
y = 1.0;
----------
x = 3;
y = 2.0;
----------
==========
)OUT", true, {"--restart", "constant", "--restart-base", "100"},
          restart_float_output);
      }
    };

    Create c;
  }

}}

// STATISTICS: test-flatzinc

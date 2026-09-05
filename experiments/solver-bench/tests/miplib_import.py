#!/usr/bin/env python3
"""Tiny exact checks for the deliberately restricted binary MPS importer."""
from fractions import Fraction
import itertools
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import miplib_import as mps
import validate

TOY="""NAME TOY
OBJSENSE
 MAX
ROWS
 N OBJ
 G ge
 L le
 E eq
COLUMNS
 M0 'MARKER' 'INTORG'
 x OBJ 0.25 ge 1.5
 x le 1 eq 1
 y OBJ -0.50 ge 0.5
 y le 2 eq -1
 M1 'MARKER' 'INTEND'
RHS
 RHS ge 0.5 le 3
 RHS eq 0 OBJ 1.25
BOUNDS
 UP B x 1
 UP B y 1
ENDATA
"""


def require(condition,message):
    if not condition: raise AssertionError(message)


def rejected(text):
    try: mps.parse_mps(text)
    except (ValueError,ZeroDivisionError): return
    raise AssertionError("unsupported MPS feature was accepted")


def main():
    p,meta=mps.parse_mps(TOY)
    require(p["c"]==[-1,2] and meta["objective_scale"]==4,"MAX/decimal objective conversion")
    require(meta["column_names"]==["x","y"] and meta["original_objective_offset"]=="-5/4","mapping or offset lost")
    for x,y in itertools.product((0,1),repeat=2):
        expected=(Fraction(3,2)*x+Fraction(1,2)*y>=Fraction(1,2) and x+2*y<=3 and x-y==0)
        feasible,objective=validate.linear_check(p,[x,y])
        require(feasible==expected,"row sign/equality/scaling changed feasible set")
        original=meta["sign"]*Fraction(objective,meta["objective_scale"])+Fraction(meta["original_objective_offset"])
        require(original==Fraction(1,4)*x-Fraction(1,2)*y-Fraction(5,4),"objective recovery lost constant")
    # Explicit BV declarations can replace integer markers, but numeric0..1
    # bounds alone cannot convert a continuous variable into a binary one.
    unmarked=TOY.replace(" M0 'MARKER' 'INTORG'\n","").replace(" M1 'MARKER' 'INTEND'\n","")
    rejected(unmarked)
    binary=unmarked.replace(" UP B x 1"," BV B x").replace(" UP B y 1"," BV B y")
    require(mps.parse_mps(binary)[0]==p,"BV and marked-binary models differ")
    fixed=TOY.replace(" UP B x 1"," FX B x 0")
    fixed_model,_=mps.parse_mps(fixed)
    require(not any(validate.linear_check(fixed_model,list(a))[0] for a in itertools.product((0,1),repeat=2)),"fixed binary bound ignored")
    bad_cases=[
        TOY.replace(" UP B x 1"," UP B x 2"),
        TOY.replace(" UP B x 1"," FR B x"),
        TOY.replace(" UP B x 1"," UP B x 0.5"),
        TOY.replace("BOUNDS\n","RANGES\n RNG ge 1\nBOUNDS\n"),
        TOY.replace("BOUNDS\n","SOS\nBOUNDS\n"),
        TOY.replace(" RHS eq 0 OBJ 1.25"," RHS2 eq 0 OBJ 1.25"),
        TOY.replace(" UP B y 1"," UP OTHER y 1"),
        TOY.replace(" N OBJ"," N OBJ\n N FREE"),
        TOY.replace(" x le 1 eq 1"," x OBJ 1 eq 1"),
        TOY.replace("1.5","NaN"), TOY.replace("1.5","1/3"),
        TOY.replace("0.25","1000000001"),
        TOY.replace(" M1 'MARKER' 'INTEND'\n", ""),
        TOY.replace("ENDATA\n",""), TOY+"MORE\n",
    ]
    for text in bad_cases: rejected(text)
    require(mps.number("1D-2")==Fraction(1,100),"exact scientific notation rejected")
    for name,(n,rows,optimum,sha) in mps.MODELS.items():
        model,meta=mps.parse_mps((mps.CACHE/(name+".mps")).read_text())
        require(model["n"]==n and meta["original_rows"]==rows,"official catalogue dimensions differ")
        saved=json.loads((mps.HERE/"miplib-instances"/("public_miplib3_"+name+".json")).read_text())
        require(all(saved[key]==model[key] for key in ("n","c","rows")),"saved classic differs from parsed original")
        require(saved["reference"]["input_sha256"]==validate.input_hash(model),"stale classic reference")
        require("incumbent" not in saved,"unexpected reference-informed incumbent")
    print("PASS binary MPS exact signs, scaling, offset, fixed bounds,15 rejection cases,and5 whole official classics")


if __name__=="__main__": main()

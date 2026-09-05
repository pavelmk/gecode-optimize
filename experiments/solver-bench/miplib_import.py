#!/usr/bin/env python3
"""Strict exact MPS subset and five unchanged MIPLIB 3.0 binary classics.

Supported: one objective, ROWS/COLUMNS/RHS/BOUNDS, INTORG/INTEND and BV,
optional OBJSENSE MIN/MAX, binary or fixed-binary bounds. Rejects RANGES, SOS,
quadratic/indicator records, multiple RHS/bound vectors, continuous/general
integer columns, implicit continuation fields, and coefficients beyond limits.
Names containing embedded whitespace are outside this explicit MPS subset.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import time

import public_catalog
import validate

HERE=Path(__file__).resolve().parent
CACHE=HERE/"miplib-cache"
BASE="https://miplib2010.zib.de/miplib3/"
CATALOG=BASE+"miplib3_cat.txt"
MODELS={
    "p0033":(33,16,3089,"8ccff819023237c79ef32e238a5da9348725ce9a4425d48888baf3a0b3b42628"),
    "p0201":(201,133,7615,"8352d7f121289185f443fdc67080fa9de01e5b9bf11b0bf41087fba4277c07a4"),
    "p0282":(282,241,258411,"3bf907c6aa3cbf80de7c48ca8e71dc29f5d70f6e5fffb716502bfc5c513196a1"),
    "p0548":(548,176,8691,"81fa3fb1e071cac0b72649c38196c18bca7ff6d7f2f6639776dcb0daf6bcab15"),
    "lseu":(89,28,1120,"00416576ed4adac15b62b1982cb7be9d7dcb2d6505067dd8396183ff1eac3dab"),
}


def number(token):
    if len(token)>100 or not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?",token):
        raise ValueError("MPS numeric token must be a finite decimal/scientific number")
    value=Fraction(token.replace("D","E").replace("d","e"))
    if abs(value.numerator)>10**30 or value.denominator>10**18:
        raise ValueError("MPS exact number exceeds supported magnitude/precision")
    return value


def integers(values):
    scale=1
    for value in values:
        scale=math.lcm(scale,value.denominator)
        if scale>10**12: raise ValueError("MPS exact scaling exceeds supported limit")
    result=[int(value*scale) for value in values]
    if any(abs(value)>1000000000 for value in result):
        raise ValueError("MPS scaled coefficient exceeds1e9")
    return result,scale


def parse_mps(source):
    rows={}; columns={}; rhs={}; bounds={}; integrality={}
    section=None; seen=set(); name=None; objective=None; sense="MIN"
    rhs_vector=None; bounds_vector=None; in_integer=False; ended=False
    headers={"NAME","OBJSENSE","ROWS","COLUMNS","RHS","BOUNDS","ENDATA"}
    unsupported={"RANGES","SOS","SOS1","SOS2","QUADOBJ","QMATRIX","QSECTION","QCMATRIX","INDICATORS","OBJNAME"}
    for lineno,line in enumerate(source.splitlines(),1):
        if not line.strip() or line.lstrip().startswith("*"): continue
        if ended: raise ValueError(f"MPS content after ENDATA at line{lineno}")
        tokens=line.split(); first=tokens[0]
        if first in unsupported:
            raise ValueError(f"Unsupported MPS section {first}")
        if first in headers and (len(tokens)==1 or first in ("NAME","OBJSENSE")):
            if first in seen: raise ValueError(f"Repeated MPS section {first}")
            if section=="COLUMNS" and in_integer: raise ValueError("unterminated INTORG marker")
            seen.add(first); section=first
            if first=="NAME":
                if len(tokens)!=2 or rows or columns: raise ValueError("MPS NAME/order")
                name=tokens[1]
            elif name is None: raise ValueError("MPS NAME required first")
            elif first=="OBJSENSE":
                if rows or len(tokens)>2: raise ValueError("MPS OBJSENSE placement")
                if len(tokens)==2:
                    if tokens[1] not in ("MIN","MAX"): raise ValueError("MPS objective direction")
                    sense=tokens[1]; section="OBJSENSE_DONE"
            elif first=="ROWS":
                if columns: raise ValueError("MPS ROWS/order")
            elif first=="COLUMNS":
                if not rows or objective is None: raise ValueError("MPS requires objective and ROWS")
            elif first in ("RHS","BOUNDS","ENDATA"):
                if not columns: raise ValueError("MPS COLUMNS required")
                if first=="ENDATA": ended=True
            continue
        if section=="OBJSENSE":
            if len(tokens)!=1 or first not in ("MIN","MAX"): raise ValueError("MPS objective direction")
            sense=first; section="OBJSENSE_DONE"
        elif section=="ROWS":
            if len(tokens)!=2 or first not in ("N","L","G","E") or tokens[1] in rows:
                raise ValueError("MPS ROWS entry")
            row=tokens[1]; rows[row]=first
            if first=="N":
                if objective is not None: raise ValueError("Multiple/free N rows unsupported")
                objective=row
        elif section=="COLUMNS":
            if len(tokens)==3 and tokens[1]=="'MARKER'":
                marker=tokens[2]
                if marker=="'INTORG'" and not in_integer: in_integer=True
                elif marker=="'INTEND'" and in_integer: in_integer=False
                else: raise ValueError("MPS integer marker sequence")
                continue
            if len(tokens) not in (3,5): raise ValueError("MPS column/continuation entry")
            column=first
            if column not in columns:
                columns[column]={}; integrality[column]=in_integer; bounds[column]=[Fraction(0),None]
            elif integrality[column]!=in_integer:
                raise ValueError("Column appears inside and outside integer markers")
            for at in range(1,len(tokens),2):
                row=tokens[at]
                if row not in rows or row in columns[column]: raise ValueError("MPS unknown/duplicate coefficient row")
                columns[column][row]=number(tokens[at+1])
        elif section=="RHS":
            if len(tokens) not in (3,5): raise ValueError("MPS RHS/continuation entry")
            if rhs_vector is None: rhs_vector=first
            if first!=rhs_vector: raise ValueError("Multiple RHS vectors unsupported")
            for at in range(1,len(tokens),2):
                row=tokens[at]
                if row not in rows or row in rhs: raise ValueError("MPS unknown/duplicate RHS row")
                rhs[row]=number(tokens[at+1])
        elif section=="BOUNDS":
            if len(tokens) not in (3,4): raise ValueError("MPS bound entry")
            kind,vector,column=tokens[:3]
            if column not in columns: raise ValueError("MPS bound on unknown column")
            if bounds_vector is None: bounds_vector=vector
            if vector!=bounds_vector: raise ValueError("Multiple bound vectors unsupported")
            if kind=="BV" and len(tokens)==3:
                integrality[column]=True; bounds[column]=[Fraction(0),Fraction(1)]
            elif kind in ("LO","UP","FX","LI","UI") and len(tokens)==4:
                value=number(tokens[3])
                if kind in ("LI","UI"): integrality[column]=True
                if kind in ("LO","LI","FX"): bounds[column][0]=value
                if kind in ("UP","UI","FX"): bounds[column][1]=value
            else: raise ValueError(f"Unsupported MPS bound type/arity {kind}")
        else:
            raise ValueError(f"Unsupported MPS input at line{lineno}")
    if not ended or objective is None: raise ValueError("MPS objective/ENDATA missing")
    if not 1<=len(columns)<=10000: raise ValueError("MPS column count exceeds driver limit")
    column_names=list(columns)
    for column in column_names:
        lo,hi=bounds[column]
        if not integrality[column]: raise ValueError(f"Continuous column unsupported: {column}")
        if lo not in (0,1) or hi not in (0,1) or lo>hi:
            raise ValueError(f"General integer/nonbinary bounds unsupported: {column}")
    sign=1 if sense=="MIN" else -1
    c,objective_scale=integers([sign*columns[column].get(objective,Fraction(0)) for column in column_names])
    model={"n":len(columns),"c":c,"rows":[]}; row_scales={}
    for row,kind in rows.items():
        if kind=="N": continue
        values=[columns[column].get(row,Fraction(0)) for column in column_names]+[rhs.get(row,Fraction(0))]
        scaled,scale=integers(values); row_scales[row]=scale
        for row_sign in ((1,-1) if kind=="E" else ((1,) if kind=="G" else (-1,))):
            model["rows"].append({"a":[[j,row_sign*v] for j,v in enumerate(scaled[:-1]) if v],"b":row_sign*scaled[-1]})
    for j,column in enumerate(column_names):
        lo,hi=bounds[column]
        if lo==1: model["rows"].append({"a":[[j,1]],"b":1})
        if hi==0: model["rows"].append({"a":[[j,-1]],"b":0})
    if len(model["rows"])>10000 or model["n"]*len(model["rows"])>10000000:
        raise ValueError("MPS transformed matrix exceeds driver size limit")
    if sum(v for v in c if v>0)>2147483646 or sum(v for v in c if v<0)<-2147483646:
        raise ValueError("MPS objective range exceeds Gecode limits")
    validate.check_instance(model)
    metadata={"name":name,"column_names":column_names,"original_rows":len(rows)-1,
              "original_sense":sense,"objective_scale":objective_scale,
              "original_objective_offset":str(-rhs.get(objective,Fraction(0))),
              "objective_recovery":"original_objective = sign * solver_objective / objective_scale + original_objective_offset",
              "sign":sign,"row_scales":row_scales}
    return model,metadata


def generate(cache=CACHE,output=HERE):
    cache,output=Path(cache),Path(output)
    directory=output/"miplib-instances"; directory.mkdir(parents=True,exist_ok=True)
    records=[]
    for name,(n,m,optimum,expected_sha) in MODELS.items():
        started=time.perf_counter()
        raw=(cache/(name+".mps")).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected_sha: raise ValueError("Changed official MIPLIB payload")
        p,metadata=parse_mps(raw.decode("ascii"))
        if p["n"]!=n or metadata["original_rows"]!=m: raise ValueError("MIPLIB catalog dimension mismatch")
        offset=Fraction(metadata["original_objective_offset"])
        transformed=metadata["sign"]*metadata["objective_scale"]*(Fraction(optimum)-offset)
        if transformed.denominator!=1: raise ValueError("Reference outside transformed objective lattice")
        identity="public_miplib3_"+name
        p.update(id=identity,family="miplib3_binary",kind="binary",tier="public",split="public",seed=None,
                 label="MIPLIB3.0 classic "+name)
        p["reference"]={"status":"optimal","objective":int(transformed),"input_sha256":validate.input_hash(p),
                        "source_url":CATALOG,"original_objective":optimum,
                        "method":"official MIPLIB3.0 catalogue marks this integer solution optimal; objective transformed exactly",
                        "used_for_solver_initialization":False}
        p["provenance"]={"suite":"MIPLIB3.0 (January1996)","not_miplib2017_benchmark_claim":True,
                         "source_url":BASE+"miplib3/"+name+".mps.gz","source_sha256":expected_sha,
                         "whole_original_instance":True,"parser":metadata,
                         "source_attribution":"Original MPS header and official catalogue retained in miplib-cache"}
        # Only two trivial, reference-free candidate assignments are attempted.
        for witness in ([0]*n,[1]*n):
            checked=validate.validate_assignment(p,witness)
            if checked["valid"]:
                p.update(incumbent=witness,incumbent_objective=checked["objective"],incumbent_method="trivial all-zero/all-one witness, independent of reference")
                break
        if "incumbent" not in p: p["incumbent_method"]="none; cold start; no published solution imported"
        p["construction_ms"]=(time.perf_counter()-started)*1000
        stem=directory/identity; stem.with_suffix(".json").write_text(json.dumps(p,indent=2)+"\n")
        stem.with_suffix(".txt").write_text(public_catalog.encode(p))
        records.append({key:p[key] for key in ("id","family","kind","tier","split","seed","label")}
                       | {"json":str(stem.with_suffix(".json").relative_to(output)),"txt":str(stem.with_suffix(".txt").relative_to(output))})
    manifest={"schema_version":1,"instances":records,"selection":"five small pure-binary MIPLIB3.0 classics selected before solver timing; no2017-benchmark-set claim",
              "warm_start":"No official solution used. Cases without trivial feasible witness run cold even if warm flag requested."}
    (output/"miplib-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return records


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache",type=Path,default=CACHE); parser.add_argument("--output",type=Path,default=HERE)
    args=parser.parse_args(); print(f"Imported {len(generate(args.cache,args.output))} complete MIPLIB3.0 binary classics")

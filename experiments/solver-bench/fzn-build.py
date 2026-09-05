#!/usr/bin/env python3
"""Build the stock and modified native FlatZinc frontends in isolated trees.

This compatibility track enables integer, set and float domains but does not
translate FlatZinc to the experimental LP module. Neither binary uses HiGHS.
The Python 3.12+ source-verification helpers come from the adjacent build.py.
"""
import argparse
import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
import build as common

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BUILD=ROOT/"build/solver-bench"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key,default in {"stock-source":BUILD/"stock-source",
                        "stock-build":BUILD/"stock-fzn",
                        "modified-build":BUILD/"enhanced-fzn",
                        "out":BUILD/"bin"}.items():
        parser.add_argument("--"+key,type=Path,default=default)
    parser.add_argument("--jobs",type=int,default=6)
    parser.add_argument("--skip-build",action="store_true")
    args=parser.parse_args()
    if sys.version_info<(3,12): parser.error("Python 3.12+ is required")
    if args.jobs<1: parser.error("--jobs must be positive")
    for name,value in vars(args).items():
        if isinstance(value,Path): setattr(args,name,value.resolve())
    compiler=shutil.which("clang++") or shutil.which("c++")
    cmake=shutil.which("cmake")
    if not compiler or not cmake or not shutil.which("git"):
        parser.error("Git, CMake and a C++ compiler must be on PATH")
    args.out.mkdir(parents=True,exist_ok=True)
    metadata={"status":"building","started_utc":datetime.now(timezone.utc).isoformat(),
              "baseline_commit":common.BASELINE,"commands":[],
              "paths":{k:str(v) for k,v in vars(args).items() if isinstance(v,Path)},
              "platform":platform.platform(),"machine":platform.machine(),
              "skip_build":args.skip_build,"lp_extension_used":False,
              "track":"Original native FlatZinc compatibility/regression; no automatic LP translation"}
    run=common.Runner(metadata)
    try:
        metadata["compiler"]=run([compiler,"--version"],True).decode()
        metadata["cmake"]=run([cmake,"--version"],True).decode()
        archive=run(["git","archive",common.BASELINE],True)
        common.extract_if_missing(args.stock_source,archive)
        metadata["stock_source_verification"]=common.verify_archive(
            args.stock_source,archive,(args.stock_build,args.stock_source/"build",args.stock_source/"experiments"))
        metadata["modified_sources"]=common.source_hashes(run)
        options={"CMAKE_BUILD_TYPE":"Release","BUILD_SHARED_LIBS":"OFF",
                 "GECODE_BUILD_SHARED":"OFF","GECODE_BUILD_STATIC":"ON",
                 "BUILD_TESTING":"OFF","GECODE_ENABLE_INT_VARS":"ON",
                 "GECODE_ENABLE_SET_VARS":"ON","GECODE_ENABLE_FLOAT_VARS":"ON",
                 "GECODE_ENABLE_SEARCH":"ON","GECODE_ENABLE_MINIMODEL":"ON",
                 "GECODE_ENABLE_DRIVER":"ON","GECODE_ENABLE_FLATZINC":"ON",
                 "GECODE_ENABLE_EXAMPLES":"OFF","GECODE_ENABLE_QT":"OFF",
                 "GECODE_ENABLE_GIST":"OFF","GECODE_ENABLE_CPPROFILER":"OFF",
                 "GECODE_ENABLE_MPFR":"OFF"}
        if platform.system()=="Darwin": options["CMAKE_OSX_DEPLOYMENT_TARGET"]="15.7"
        metadata["cmake_options"]={"stock":options,"modified":dict(options,GECODE_ENABLE_LP_RELAXATION="OFF")}
        for label,source,folder in [("stock",args.stock_source,args.stock_build),
                                    ("modified",ROOT,args.modified_build)]:
            opts=metadata["cmake_options"][label]
            if not args.skip_build:
                run([cmake,"-S",source,"-B",folder,"-DCMAKE_CXX_COMPILER="+compiler,
                     *[f"-D{k}={v}" for k,v in opts.items()]])
                run([cmake,"--build",folder,"--parallel",args.jobs,"--target","fzn-gecode"])
            metadata.setdefault("caches",{})[label]=common.verify_cache(folder,source,opts)
            executable=folder/"bin/fzn-gecode"
            name="stock-fzn" if label=="stock" else "enhanced-fzn"
            shutil.copy2(executable,args.out/name)
            metadata.setdefault("binary_hashes",{})[name]=common.file_hash(args.out/name)
            metadata.setdefault("library_hashes",{})[label]={p.name:common.file_hash(p) for p in sorted(folder.glob("libgecode*.a"))}
        metadata["status"]="built"
    except Exception as error:
        metadata["status"]="failed";metadata["error"]=f"{type(error).__name__}: {error}"
        raise
    finally:
        metadata["finished_utc"]=datetime.now(timezone.utc).isoformat()
        payload=json.dumps(metadata,indent=2,sort_keys=True)+"\n"
        (args.out/"fzn-build-metadata.json").write_text(payload)
        (HERE/"results").mkdir(exist_ok=True)
        (HERE/"results/fzn-build-metadata.json").write_text(payload)


if __name__=="__main__": main()

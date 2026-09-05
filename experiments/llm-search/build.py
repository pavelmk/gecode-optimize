#!/usr/bin/env python3
"""Build pinned stock and modified Gecode with matching settings, then tests/drivers."""
import argparse
import io
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

BASELINE = "3e0e8ee76fb4ba01c53616dce02c0bb1a53f159e"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def run(args):
    print(" ".join(map(str,args)), flush=True)
    subprocess.run(list(map(str,args)), check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stock-source",type=Path,default=ROOT/"build/llm-search/stock-source")
    p.add_argument("--stock-build",type=Path,default=ROOT/"build/llm-search/stock")
    p.add_argument("--modified-build",type=Path,default=ROOT/"build/llm-search/modified")
    p.add_argument("--out",type=Path,default=ROOT/"build/llm-search/bin")
    p.add_argument("--skip-libraries",action="store_true")
    p.add_argument("--jobs",type=int,default=6)
    a=p.parse_args()
    cmake=shutil.which("cmake") or "/opt/homebrew/bin/cmake"
    compiler=shutil.which("clang++") or shutil.which("c++")
    # Always verify the stock source against the pinned Git archive. An existing
    # source directory must not silently become a modified comparison baseline.
    archive=subprocess.check_output(["git","-C",str(ROOT),"archive",BASELINE])
    if not a.stock_source.exists():
        a.stock_source.parent.mkdir(parents=True,exist_ok=True)
        temporary=Path(tempfile.mkdtemp(prefix="stock-extract-",dir=a.stock_source.parent))
        try:
            with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
                tf.extractall(temporary,filter="data")
            temporary.rename(a.stock_source)
        finally:
            if temporary.exists(): shutil.rmtree(temporary)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
        expected=set()
        for member in tf.getmembers():
            expected.add(member.name)
            actual=a.stock_source/member.name
            if member.isfile():
                if not actual.is_file() or hashlib.sha256(actual.read_bytes()).digest()!=hashlib.sha256(tf.extractfile(member).read()).digest():
                    raise RuntimeError(f"Stock source differs from pinned baseline: {member.name}")
            elif member.issym() and (not actual.is_symlink() or os.readlink(actual)!=member.linkname):
                raise RuntimeError(f"Stock source symlink differs: {member.name}")
        for actual in (a.stock_source/"gecode").rglob("*"):
            if actual.is_file() and str(actual.relative_to(a.stock_source)) not in expected:
                raise RuntimeError(f"Unexpected file in stock solver source: {actual}")
    if not a.skip_libraries:
        for source,build in [(a.stock_source,a.stock_build),(ROOT,a.modified_build)]:
            options=["-DCMAKE_BUILD_TYPE=Release","-DBUILD_SHARED_LIBS=OFF",
                     "-DGECODE_BUILD_SHARED=OFF","-DGECODE_BUILD_STATIC=ON","-DBUILD_TESTING=OFF"]
            for name in ["EXAMPLES","QT","GIST","CPPROFILER","SET_VARS","FLOAT_VARS",
                         "DRIVER","FLATZINC","MPFR"]:
                options.append(f"-DGECODE_ENABLE_{name}=OFF")
            if platform.system()=="Darwin":
                options.append("-DCMAKE_OSX_DEPLOYMENT_TARGET=15.7")
            run([cmake,"-S",source,"-B",build,*options])
            run([cmake,"--build",build,"--parallel",a.jobs,"--target",
                 "gecodeminimodel_static","gecodesearch_static"])
    a.out.mkdir(parents=True,exist_ok=True)
    common=[compiler,"-std=c++17","-O3","-DNDEBUG","-DGECODE_NO_AUTOLINK"]
    if platform.system()=="Darwin": common.append("-mmacosx-version-min=15.7")
    def compile(name,sources,source,build,experimental):
        flags=[*common,"-I"+str(build),"-I"+str(source)]
        if experimental: flags.append("-DGECODE_EXPERIMENTAL")
        run([*flags,*sources,"-L"+str(build),"-lgecodeminimodel","-lgecodeint",
             "-lgecodesearch","-lgecodekernel","-lgecodesupport","-pthread","-o",a.out/name])
    compile("stock",[HERE/"driver.cpp"],a.stock_source,a.stock_build,False)
    compile("modified",[HERE/"driver.cpp"],ROOT,a.modified_build,True)
    for test in ["checkpoint","cliques"]:
        compile("test-"+test,[HERE/"tests"/(test+".cpp")],ROOT,a.modified_build,True)
    compile("test-upstream-search",[ROOT/"test/test.cpp",ROOT/"test/search.cpp"],
            ROOT,a.modified_build,True)
    metadata={"baseline_commit":BASELINE,"compiler":subprocess.check_output([compiler,"--version"],text=True),
              "platform":platform.platform(),"machine":platform.machine(),"flags":common,
              "stock_source":str(a.stock_source.resolve()),"stock_build":str(a.stock_build.resolve()),
              "modified_source":str(ROOT),"modified_build":str(a.modified_build.resolve())}
    (a.out/"build-metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    (HERE/"results").mkdir(exist_ok=True)
    (HERE/"results/build-metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")


if __name__=="__main__": main()

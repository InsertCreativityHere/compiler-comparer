#!/usr/bin/env python

import glob;
import os;
from pathlib import Path;
import subprocess;
import sys;
import time;



# Setting this to true will cause the script to print lots of letters to the terminal while it's running.
DEBUGGING = False;

# This is passed into many of the subprocess commands we execute.
# `None` causes 'stdout' to be dumped into the terminal, whereas `DEVNULL` will eat this output.
# Note that we only use this for 'stdout', we always let 'stderr' dump into the terminal.
OUTPUT_TO = None if DEBUGGING else subprocess.DEVNULL;

# Prevent git commands from prompting for user input within the script.
ENVIRONMENT = os.environ.copy();
ENVIRONMENT["GIT_ASK_YESNO"] = "false";

# Get the current directory now, we'll need it later.
CURRENT_DIR = os.getcwd();
if DEBUGGING: print("    >> CURRENT_DIR = '" + str(CURRENT_DIR) + "'");

# Determine if we're running on a windows platform.
IS_WINDOWS = os.name == "nt";
if DEBUGGING: print("    >> IS_WINDOWS = '" + str(CURRENT_DIR) + "'");






# Before anything else, make sure the user is VERY AWARE that this will clean and reset their repo...
print("!!! ------------------------------------------------- !!!");
print("!!! BE WARNED THIS SCRIPT WILL CLEAN THE CURRENT REPO !!!");
print("!!! DO NOT RUN THIS IF YOU HAVE ANY UNSAVED WORK LEFT !!!");
print("!!! ------------------------------------------------- !!!");
input("Press Enter to continue...");
print();




def printHelp():
    print("TODO");




#### ============================ ####
#### Parse Command Line Arguments ####
#### ============================ ####

# Declare all the parameters this script can accept.
compilers = [];
branches = [];
sliceFiles = [];
projPath = "";
compilersPath = "";
pythonPath = "";

# Define all the command-line switches for specifying parameters.
SHORT_COMPILER = "-c=";
LONG_COMPILER = "--compiler=";
SHORT_BRANCH = "-b=";
LONG_BRANCH = "--branch=";
PROJ_PATH = "--proj-path=";
COMPILERS_PATH = "--compilers-path=";
PYTHON_PATH = "--python-path=";

# Perform the actual parsing.
if DEBUGGING: print("    >> Provided arguments: " + str(sys.argv[1:]));
for index, arg in enumerate(sys.argv[1:]):
    if arg.startswith(SHORT_COMPILER):
        compilers.append(arg[len(SHORT_COMPILER):]);
        if DEBUGGING: print("    >> Parsed '" + compilers[-1] + "' from '" + SHORT_COMPILER + "'");
    elif arg.startswith(LONG_COMPILER):
        compilers.append(arg[len(LONG_COMPILER):]);
        if DEBUGGING: print("    >> Parsed '" + compilers[-1] + "' from '" + LONG_COMPILER + "'");
    elif arg.startswith(SHORT_BRANCH):
        branches.append(arg[len(SHORT_BRANCH):]);
        if DEBUGGING: print("    >> Parsed '" + branches[-1] + "' from '" + SHORT_BRANCH + "'");
    elif arg.startswith(LONG_BRANCH):
        branches.append(arg[len(LONG_BRANCH):]);
        if DEBUGGING: print("    >> Parsed '" + branches[-1] + "' from '" + LONG_BRANCH + "'");
    elif arg.startswith(PROJ_PATH):
        projPath = arg[len(PROJ_PATH):];
        if DEBUGGING: print("    >> Parsed '" + projPath + "' from '" + PROJ_PATH + "'");
    elif arg.startswith(COMPILERS_PATH):
        compilersPath = arg[len(COMPILERS_PATH):];
        if DEBUGGING: print("    >> Parsed '" + compilersPath + "' from '" + COMPILERS_PATH + "'");
    elif arg.startswith(PYTHON_PATH):
        pythonPath = arg[len(PYTHON_PATH):];
        if DEBUGGING: print("    >> Parsed '" + pythonPath + "' from '" + PYTHON_PATH + "'");
    elif arg == "--help":
        printHelp();
        if DEBUGGING: print("    >> Emitted help message");
        exit(0);
    elif arg == "--":
        sliceFiles.extend(sys.argv[index+1:]);
        if DEBUGGING: print("    >> Entered argument mode at index '" + str(index) + "'. There were '" + str(len(sys.argv[index+1:])) + "' arguments left");
        break;
    else:
        sliceFiles.append(arg);
        if DEBUGGING: print("    >> Parsed '" + sliceFiles[-1] + "' as a Slice file");

if DEBUGGING:
    print();
    print("    >> ================================================");
    print("    >> Finished argument parsing with these parameters:");
    print("    >> ================================================");
    print("    >> compilers = '" + str(compilers) + "'");
    print("    >> branches = '" + str(branches) + "'");
    print("    >> sliceFiles = '" + str(sliceFiles) + "'");
    print("    >> projPath = '" + str(projPath) + "'");
    print("    >> compilersPath = '" + str(compilersPath) + "'");
    print();




#### ============================================ ####
#### Compute Defaults for and Sanitize Parameters ####
#### ============================================ ####

# Find the root of the repository. This is also a test that git is usable in the current directory.
result = subprocess.run(["git", "rev-parse", "--show-toplevel"], check=True, capture_output=True);
if DEBUGGING: print("    >> RESULT 'git rev-parse --show-toplevel' = '" + str(result) + "'");
REPO_ROOT = result.stdout.decode("utf-8").strip();
if DEBUGGING: print("    >> REPO_ROOT = '" + str(REPO_ROOT) + "'\n");
if not os.path.isdir(REPO_ROOT):
    print("ERROR: Expected repository root to be at '" + REPO_ROOT + "', but no such directory exists!");
    exit(11);

# If no compilers were specified, we want to run _all_ the compilers.
if len(compilers) == 0:
    compilers = ["ice2slice", "slice2cpp", "slice2cs", "slice2java", "slice2js", "slice2matlab", "slice2php", "slice2py", "slice2rb", "slice2swift"];
    # We don't build 'slice2swift' on windows. TODO we should fix this in the future.
    if IS_WINDOWS:
        compilers.remove("slice2swift");
    if DEBUGGING: print("    >> No compilers were specified. Setting to '" + str(compilers) + "'");

# If no branches were specified, running this script is useless...
if len(branches) == 0:
    print("Error: At least one branch must be specified!");
    printHelp();
    exit(13);

# If no slice files were provided, we want to recursively get ALL the slice files in the current directory.
if len(sliceFiles) == 0:
    sliceFiles = [CURRENT_DIR];
    if DEBUGGING: print("    >> No Slice files were specified. Setting to '" + str(CURRENT_DIR) + "'");
# Check for any directories that were passed in as Slice files.
# We recursively check each of these directories for Slice files and use those instead.
tempSliceFiles = sliceFiles.copy();
sliceFiles = [];
for file in tempSliceFiles:
    if os.path.isdir(file):
        globPattern = os.path.join(file, "**/*.ice");
        if DEBUGGING: print("    >> Encountered Slice directory of '" + file + "', globbing for '" + str(globPattern) + "'");
        sliceFiles.extend(glob.iglob(globPattern, recursive=True));
    else:
        sliceFiles.append(file);
if DEBUGGING:
    print();
    print("    >> (resolved) sliceFiles = '" + str(sliceFiles) + "'");
    print();

# If no project path was specified, set it to the top-level project file.
if len(projPath) == 0:
    # Check whether we're running on a Windows platform or not.
    if IS_WINDOWS:
        projPath = os.path.join(REPO_ROOT, "cpp\\msbuild\\ice.proj");
        if DEBUGGING: print("    >> No project path was specified. Setting to '" + str(projPath) + "' for windows");
    else:
        print("This script doesn't really work on non-windows platforms, sorry...")
        exit(101); #TODO make this work on non-windows platforms!
    # Make sure that whatever file we just set it to actually exists.
    if not os.path.isfile(projPath):
        print("ERROR: Default computed project path '" + str(projPath) + "' does not exist!");
        print("You'll have to manually specify the project path with '--proj-path=<PATH>...");
        exit(14);

# If no compiler path was specified, we compute one from the REPO_ROOT based on the platform.
if len(compilersPath) == 0:
    # Check whether we're running on a Windows platform or not.
    if IS_WINDOWS:
        compilersPath = os.path.join(REPO_ROOT, "cpp\\bin\\x64\\Debug");
        if DEBUGGING: print("    >> No compiler path was specified. Setting to '" + str(compilersPath) + "' for windows");
    else:
        compilersPath = os.path.join(REPO_ROOT, "cpp/bin");
        if DEBUGGING: print("    >> No compiler path was specified. Setting to '" + str(compilersPath) + "' for unix");
# Now that we know we have a compiler path, add it onto all the compilers, so they're easier to run later on.
compilers = [os.path.join(compilersPath, c) for c in compilers];
# We have to add '.exe' to the paths if we're running on Windows.
if IS_WINDOWS:
    compilers = [c + ".exe" for c in compilers];
if DEBUGGING: print("    >> (sanitized) compilers = '" + str(compilers) + "'");

# If no python path was specified, we get the path for the 'python' that this script is running in.
if len(pythonPath) == 0:
    pythonPath = sys.exec_prefix
    if DEBUGGING: print("    >> No python path was specified. Setting to '" + str(pythonPath) + "'");

# Final step if we've gotten this far is to sanitize the Slice file paths.
# We want forward slashes only, and to make sure that all the paths live in the repository.
sliceFiles = [os.path.abspath(f).replace('\\', '/') for f in sliceFiles];
sanitizedRepoRoot = REPO_ROOT.replace('\\', '/') + '/';
if DEBUGGING: print("    >> 'sanitizedRepoRoot' = '" + str(sanitizedRepoRoot) + "'");
for f in sliceFiles:
    if not f.startswith(sanitizedRepoRoot):
        print("ERROR: This script cannot be run on '" + f + "' since it lives outside of the repository.");
    if not os.path.exists(f):
        print("ERROR: The Slice file '" + f + "' does not exist.");
# Remove the REPO_ROOT from the slice Files, and filter out any files which live outside of the repository.
sliceFiles = [f[len(sanitizedRepoRoot):] for f in sliceFiles if (f.startswith(sanitizedRepoRoot) and os.path.isfile(f))];
if DEBUGGING:
    print();
    print("    >> (sanitized) sliceFiles = '" + str(sliceFiles) + "'");
    print();
print("A total of " + str(len(sliceFiles)) + " Slice files will be compiled.");




#### ============================================= ####
#### Define Functions for the Actual Runtime Logic ####
#### ============================================= ####

def git_clean():
    time.sleep(0.5);
    try:
        result = subprocess.run(["git", "clean", "-dqfx"], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
        if DEBUGGING: print("    >> RESULT 'git clean -dqfx' = '" + str(result) + "'");
    except subprocess.CalledProcessError as ex:
        print(ex);
        print("WARNING: failed to 'git clean' repository, continuing anyways...");
        print();

def git_reset():
    time.sleep(0.5);
    try:
        result = subprocess.run(["git", "reset", "--hard"], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
        if DEBUGGING: print("    >> RESULT 'git reset --hard' = '" + str(result) + "'");
    except subprocess.CalledProcessError as ex:
        print(ex);
        print("WARNING: failed to 'git reset' repository, continuing anyways...");
        print();

def git_checkout(branchName):
    time.sleep(0.5);
    result = subprocess.run(["git", "checkout", branchName], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
    if DEBUGGING: print("    >> RESULT 'git checkout <branchName>' = '" + str(result) + "'");

def msbuild():
    time.sleep(0.5);
    result = subprocess.run(["msbuild", projPath, "/target:BuildDist", "/p:Configuration=Debug", "/p:Platform=x64", "/p:PythonHome=\"" + pythonPath + "\"", "/m", "/nr:false"], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
    if DEBUGGING: print("    >> RESULT 'msbuild <projPath>' = '" + str(result) + "'");

def sliceCompile(compiler, sliceFile, outputDir):
    time.sleep(0.02);
    result = subprocess.run([compiler, "--output-dir", outputDir, "-I./slice", "-I" + os.path.dirname(sliceFile), sliceFile], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
    if DEBUGGING: print("    >> RESULT '" + str(compiler) + "--output-dir <outputPath> -Islice -I<parentPath> <file>' = '" + str(result) + "'");




#### ================================= ####
#### Let's Actually Do Some Stuff Now! ####
#### ================================= ####

# First, navigate to the repo root. It's easier if we're running in a known location.
os.chdir(REPO_ROOT);

# Then, do a preliminary clean and reset, to make sure we're in a known state.
git_clean();
git_reset();

# Then, we want to compile the slice Files against each provided branch.
for branch in branches:
    print();

    # Checkout the branch, and perform a clean build.
    print("Beginning build of '" + branch + "' branch...");
    if DEBUGGING: print("================================================================================");
    git_checkout(branch);
    msbuild();
    if DEBUGGING: print("================================================================================");
    print("    Build complete!");

    # If the build succeeded, next we want to run the Slice compilers over the Slice files.
    # So we create a directory to output the generated code into, and then run through the compilers.
    outputDirBase = os.path.join(REPO_ROOT, "_slice_generated_" + branch);
    Path(outputDirBase).mkdir(parents=True, exist_ok=True);
    for compiler in compilers:
        print("    Running " + os.path.basename(compiler) + "...");
        for file in sliceFiles:
            outputDir = os.path.join(outputDirBase, os.path.dirname(file));
            Path(outputDir).mkdir(parents=True, exist_ok=True);
            sliceCompile(compiler, "./" + file, outputDir);

    # We're done with this branch!
    print("Finished!");

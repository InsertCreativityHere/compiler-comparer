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
if DEBUGGING: print("    >> IS_WINDOWS = '" + str(IS_WINDOWS) + "'");






# Before anything else, make sure the user is VERY AWARE that this will clean and reset their repo...
print();
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

# Parse any command line arguments.
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
    #TODO We don't build 'slice2swift' on windows... we should fix this in the future.
    if IS_WINDOWS:
        compilers.remove("slice2swift");
    #TODO 'ice2slice' hits an assertion when compiling constants. Unfortunately, not worth running yet.
    compilers.remove("ice2slice");
    if DEBUGGING: print("    >> No compilers were specified. Setting to '" + str(compilers) + "'");

# If no branches were specified, we default to using the current branch.
if len(branches) == 0:
    result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=True, capture_output=True);
    if DEBUGGING: print("    >> RESULT 'git rev-parse --abbrev-ref HEAD' = '" + str(result) + "'");
    branches = [result.stdout.decode("utf-8").strip()];
    if DEBUGGING: print("    >> No branches were specified. Setting to current branch '" + str(branches[0]) + "'");

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
        projPath = os.path.join(REPO_ROOT, "cpp/Makefile");
        if DEBUGGING: print("    >> No project path was specified. Setting to '" + str(projPath) + "' for unix");
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

def git_clean(removeSliceGenerated):
    time.sleep(0.5);
    try:
        args = ["git", "clean", "-dqfx"] + ([] if removeSliceGenerated else ["-e", "_slice_gen_*"]);
        result = subprocess.run(args, check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
        if DEBUGGING: print("    >> RESULT 'git clean -dqfx ...' = '" + str(result) + "'");
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
    result = subprocess.run(["git", "-c", "advice.detachedHead=false", "checkout", branchName], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
    if DEBUGGING: print("    >> RESULT 'git ... checkout <branchName>' = '" + str(result) + "'");

    result1 = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=True, capture_output=True);
    result2 = subprocess.run(["git", "rev-parse", "--short", "HEAD"], check=True, capture_output=True);
    return [result1.stdout.decode("utf-8").strip(), result2.stdout.decode("utf-8").strip()];

def build():
    time.sleep(0.5);
    if IS_WINDOWS:
        msbuild();
    else:
        make();

def msbuild():
    result = subprocess.run(["msbuild", projPath, "/target:BuildDist", "/p:Configuration=Debug", "/p:Platform=x64", "/p:PythonHome=\"" + pythonPath + "\"", "/m", "/nr:false"], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
    if DEBUGGING: print("    >> RESULT 'msbuild ...' = '" + str(result) + "'");

def make():
    args = ["make", "-C", os.path.dirname(projPath)] + [os.path.basename(c) for c in compilers];
    result = subprocess.run(args, check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
    if DEBUGGING: print("    >> RESULT 'make ...' = '" + str(result) + "'");

def sliceCompile(compiler, sliceFile, outputDir):
    time.sleep(0.01);
    result = subprocess.run([compiler, "--output-dir", outputDir, "-I./slice", "-I" + os.path.dirname(sliceFile), sliceFile], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
    if DEBUGGING: print("    >> RESULT '" + str(compiler) + "--output-dir <outputPath> -Islice -I<parentPath> <file>' = '" + str(result) + "'");

def moveDir(sourceDir, destinationDir):
    time.sleep(0.5);
    if IS_WINDOWS:
        move(sourceDir, destinationDir);
    else:
        mv(sourceDir, destinationDir);

def move(sourceDir, destinationDir):
    result = subprocess.run(["move", "/y", sourceDir, destinationDir], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
    if DEBUGGING: print("    >> RESULT 'move /y ...' = '" + str(result) + "'");

def mv(sourceDir, destinationDir):
    result = subprocess.run(["mv", "-f", sourceDir, destinationDir], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
    if DEBUGGING: print("    >> RESULT 'mv -f ...' = '" + str(result) + "'");

#### ================================= ####
#### Let's Actually Do Some Stuff Now! ####
#### ================================= ####

# First, navigate to the repo root. It's easier if we're running in a known location.
os.chdir(REPO_ROOT);

# Keep a list of all the directories we've generated, and their corresponding commit messages, for later.
generatedDirectoriesAndCommitMessage = [];

# Then, do a preliminary clean and reset, to make sure we're in a known state.
git_clean(True);
git_reset();

# Then, we want to compile the slice Files against each provided branch.
for index,branch in enumerate(branches):
    print();

    # Checkout the branch, and perform a clean build.
    if DEBUGGING: print("================================================================================");
    branchName, branchID = git_checkout(branch);
    git_clean(False);

    print("Building '" + branchName + "@" + branchID + "'...");
    build();
    if DEBUGGING: print("================================================================================");
    print("Build complete!");

    # If the build succeeded, next we want to run the Slice compilers over the Slice files.
    # So we create a directory to output the generated code into, and then run through the compilers.
    outputDirBase = os.path.join(REPO_ROOT, "_slice_gen_" + str(index) + "_" + branchName + "_" + branchID);
    Path(outputDirBase).mkdir(parents=True, exist_ok=True);

    # We also grab the commit message corresponding to this branch's latest commit.
    # So we can print it out later to improve readability and diff navigation for the end-user.
    result = subprocess.run(["git", "log", "--format=%B", "-n", "1", branchID], check=True, capture_output=True);
    branchMessage = result.stdout.decode("utf-8").strip();
    generatedDirectoriesAndCommitMessage.append([outputDirBase, branchMessage]);

    # Run all the Slice compilers!
    for compiler in compilers:
        print("    Running " + os.path.basename(compiler) + "...");
        for file in sliceFiles:
            outputDir = os.path.join(outputDirBase, os.path.dirname(file));
            Path(outputDir).mkdir(parents=True, exist_ok=True);
            sliceCompile(compiler, "./" + file, outputDir);

    # We're done with this branch!
    print("Finished!");




#### ======================================== ####
#### Check the Generated Code for Differences ####
#### ======================================== ####

if DEBUGGING:
    print();
    print("    >> ==============================================");
    print("    >> Entering File Discovery and Differencing Phase");
    print("    >> ==============================================");
    print();

# Create a new directory that we'll use as scratch space for comparing the generated code.
compareDir = os.path.join(REPO_ROOT, "_slice_compare_");
Path(compareDir).mkdir();

# Initialize a git repository in that directory. We utilize git to do the diffing for us!
result = subprocess.run(["git", "-C", compareDir, "init"], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
if DEBUGGING: print("    >> RESULT 'git ... init' = '" + str(result) + "'");
result = subprocess.run(["git", "-C", compareDir, "config", "user.name", "temp"], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
if DEBUGGING: print("    >> RESULT 'git ... config user.name temp' = '" + str(result) + "'");
result = subprocess.run(["git", "-C", compareDir, "config", "user.email", "temp@zeroc.com"], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
if DEBUGGING: print("    >> RESULT 'git ... config user.email temp@zeroc.com' = '" + str(result) + "'");

# Then, we go through the generated code for each branch run, copy their generated code into this folder, and commit them.
# So, each commit in this repository represents one of the branches that we executed a compiler run for. In order.
# Comparing any 2 commits in this repo will show you the changes (if any) in the generated code.
for generatedDir in generatedDirectories:
    copyDirContents(generatedDir, compareDir);
    # TODO # Copy generatedDirectories[0] into compareDir
    result = subprocess.run(["git", "-C", compareDir, "add", "--all"], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
    if DEBUGGING: print("    >> RESULT 'git ... add --all' = '" + str(result) + "'");
    result = subprocess.run(["git", "-C", compareDir, "commit", "-m", generatedDirectories[0][10:]], check=True, env=ENVIRONMENT, stdout=OUTPUT_TO);
    if DEBUGGING: print("    >> RESULT 'git ... commit -m ...' = '" + str(result) + "'");

# TODO add some analysis here at the end I guess.
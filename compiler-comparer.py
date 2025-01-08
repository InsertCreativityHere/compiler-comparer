#!/usr/bin/env python

import concurrent.futures;
import glob;
import os;
from pathlib import Path;
import subprocess;
import sys;
import time;
import traceback;


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

# Every `REPACK_COUNTER_MAX` cycles, we want to repack and garbage collect in our scratch repository.
# When using back-track, it's important to do this periodically, or otherwise the size of the repo
# grows out of control and slows stuff down. (This only has an effect during back-tracking).
REPACK_COUNTER_MAX = 100;








def runCommand(args, desc, checked, capture):
    if capture:
        result = subprocess.run(args, check=checked, env=ENVIRONMENT, shell=True, capture_output=True);
    else:
        result = subprocess.run(args, check=checked, env=ENVIRONMENT, shell=True, stdout=OUTPUT_TO);

    if DEBUGGING:
        if desc == None: desc = " ".join(args);
        print("    >> RESULT '" + desc + "' = '" + str(result) + "'");

    if capture:
        return (result.stdout.decode("utf-8").strip() + "\n" + result.stderr.decode("utf-8").strip()).strip();
    else:
        return None;



def printHelp():
    print(
'''
USAGE:
python compiler-comparer.py [options] [slice_files...]

'slice_files' should be separated by spaces and can be either individual files or directories.
If a file is provided it is passed directly to the Slice compilers (and should end with '.ice').
If a directory is provided, this script will recursively search for all files ending with '.ice'
within the directory and compile them.

OPTIONS:
-c, --compiler     Specifies a slice compiler that this script should run over Slice files.
                   This should be the bare name of the compiler, without any file extension.
                   For example: `--compiler=slice2java` tells the script to only run `slice2java`.
                   It is valid to provide multiple compilers; this script will run them in the
                   order they are provided.
                   If no compilers are specified, this script will automatically use _all_
                   the available Slice compilers on the current platform.

-b, --branch       Specifies which branches the script should checkout before building.
                   Actually this can be any 'treeish' including branch names, commit IDs, and tags.
                   For example: `--branch=main --branch=9100d41` tells the script to check a branch
                   named `main` and a commit with an ID of `9100d41`.
                   It is valid to provide multiple branches; this script will check them out and
                   build them in the order they are provided.
                   If no branches are specified, this script will automatically use `HEAD`.

--back-track       Instructs the script to use back-tracking.
                   Instead of checking out specific branches/commits, the script will start at
                   `HEAD~N` and build every commit (in order) until it's reached back to `HEAD`.
                   For example: `--back-track=12` tells the script to check the last 12 commits.
                   If `--back-track` is specified, it is invalid to also provide specific branches
                   with `--branch`. Only one of these options may be used at a time.

--catchup          This script outputs a git repository showing all changes in the generated code.
                   Over time, this repository can fall behind the current state of the original
                   repository, that's where this option comes in.
                   It only works if you have an already existing '_slice_compare_' directory that
                   has the results from a previous run of this script. If that's all true,
                   specifying this option instructs the script to automatically determine how many
                   commits it's behind from the current 'HEAD', and will automatically use
                   back-tracking to catch it back up to the most recent commit.
                   If `--catchup` is specified it is invalid to also provide specific branches with
                   `--branch`, or to use `--back-track`. Only one of these may be used at a time.

--proj-path        Specifies the project file path that should be used to build the compilers.
                   It shouldn't be necessary to set this if you're inside the repository,
                   the script should be able to find `cpp/msbuild/ice.proj` automatically.
                   But if it can't, or you want to build with a different project, this exists.
                   For example: `--proj-path="D:/Code/Workspace/ice/cpp/msbuild/ice.proj"`

--compilers-path   Specifies where the compilers will be built, so the script can find them.
                   It shouldn't be necessary to set this if you're inside the repository,
                   the script should be able to locate them based on the current platform.
                   But if it can't, or you want to use a different set of compilers, this exists?
                   If provided, the path should be relative to the root of the repository.
                   For example: `--compilers-path="cpp/bin"` is the expected path on unix systems.

--python-path      This is probably useless. I should probably remove it.

-p, --parallel     Instructs the script to build and run the Slice compilers in parallel.
                   You probably want this turned on.
                   Note: 'slice2java', 'slice2py', and 'slice2matlab' are always run serially due
                   to race conditions in how they generate directories and shared files.
                   But all other compilers will be run in parallel, even if used alongside one of
                   the above, and the building of the compilers themselves will also be in parallel.
'''
    );








#### ============================================= ####
#### Define Functions for the Actual Runtime Logic ####
#### ============================================= ####

def git_clean(fullClean):
    time.sleep(0.1);
    try:
        args = ["git", "clean", "-dqfx"] + ([] if fullClean else ["-e", "_slice_compare_"]);
        runCommand(args, None, checked=True, capture=False);
    except subprocess.CalledProcessError as ex:
        print(ex);
        print("WARNING: failed to 'git clean' repository, continuing anyways...");
        print();

def git_reset():
    time.sleep(0.1);
    try:
        runCommand(["git", "reset", "--hard"], None, checked=True, capture=False);
    except subprocess.CalledProcessError as ex:
        print(ex);
        print("WARNING: failed to 'git reset' repository, continuing anyways...");
        print();

def git_checkout(branchName):
    time.sleep(0.1);
    runCommand(["git", "-c", "advice.detachedHead=false", "checkout", branchName], "git ... checkout ...", checked=True, capture=False);

def git_repack(directory):
    print();
    print("repacking repository and running garbage collection pass...");

    time.sleep(0.1);
    runCommand(["git", "-C", directory, "gc"], "git -C ... gc", checked=True, capture=False);
    print();

def build(compilers, projPath, pythonPath):
    time.sleep(0.1);
    if IS_WINDOWS:
        args = ["msbuild", projPath, "/target:BuildDist", "/p:Configuration=Debug", "/p:Platform=x64", "/p:PythonHome=\"" + pythonPath + "\"", "/nr:false"];
        if runInParallel:
            args.insert(1, "/m");
        runCommand(args, "msbuild ...", checked=True, capture=False);
    else:
        args = ["make", "-C", os.path.dirname(projPath)] + [os.path.basename(c) for c in compilers];
        if runInParallel:
            args.insert(1, "-j");
        runCommand(args, "make ...", checked=True, capture=False);

def sliceCompile(compiler, sliceFile, outputDir):
    parentDir = os.path.dirname(sliceFile);
    args = [compiler, "--output-dir", outputDir, "-I./slice", "-I" + parentDir, "-I" + os.path.dirname(parentDir), sliceFile];

    # Make sure the output directory exists. The Slice compilers cannot create directories that don't already exist.
    Path(outputDir).mkdir(parents=True, exist_ok=True);

    # We set `checked=False` here to tolerate when the Slice compiler encounters errors. Otherwise one error kills this whole script.
    result = runCommand(args, os.path.basename(compiler) + " ...", checked=False, capture=True);
    return (result + "\n" if result else result);

def moveDir(sourceDir, destinationDir):
    time.sleep(0.1);
    if IS_WINDOWS:
        # The 'move' command cannot move hidden directories, so we first must make sure the 'hidden' attribute is unset.
        runCommand(["attrib", "-h", sourceDir], "move ...", checked=True, capture=False);
        runCommand(["move", "/y", sourceDir, destinationDir], "move ...", checked=True, capture=False);
    else:
        runCommand(["mv", "-f", sourceDir, destinationDir], "mv ...", checked=True, capture=False);







if __name__ == "__main__":
    #### ============================ ####
    #### Parse Command Line Arguments ####
    #### ============================ ####

    # Declare all the parameters this script can accept.
    compilers = [];
    branches = [];
    backTrack = None;
    catchup = False;
    sliceFiles = [];
    projPath = "";
    compilersPath = "";
    pythonPath = "";
    runInParallel = False;

    # Define all the command-line switches for specifying parameters.
    SHORT_COMPILER = "-c=";
    LONG_COMPILER = "--compiler=";
    SHORT_BRANCH = "-b=";
    LONG_BRANCH = "--branch=";
    BACK_TRACK = "--back-track=";
    CATCHUP = "--catchup";
    PROJ_PATH = "--proj-path=";
    COMPILERS_PATH = "--compilers-path=";
    PYTHON_PATH = "--python-path=";
    SHORT_PARALLEL = "-p";
    LONG_PARALLEL = "--parallel";

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
        elif arg.startswith(BACK_TRACK):
            backTrack = int((arg[len(BACK_TRACK):]));
            if DEBUGGING: print("    >> Parsed '" + str(backTrack) + "' from '" + BACK_TRACK + "'");
        elif arg == CATCHUP:
            catchup = True;
            if DEBUGGING: print("    >> Turning 'catchup' on because of '" + arg + "'");
        elif arg.startswith(PROJ_PATH):
            projPath = arg[len(PROJ_PATH):];
            if DEBUGGING: print("    >> Parsed '" + projPath + "' from '" + PROJ_PATH + "'");
        elif arg.startswith(COMPILERS_PATH):
            compilersPath = arg[len(COMPILERS_PATH):];
            if DEBUGGING: print("    >> Parsed '" + compilersPath + "' from '" + COMPILERS_PATH + "'");
        elif arg.startswith(PYTHON_PATH):
            pythonPath = arg[len(PYTHON_PATH):];
            if DEBUGGING: print("    >> Parsed '" + pythonPath + "' from '" + PYTHON_PATH + "'");
        elif arg == SHORT_PARALLEL or arg == LONG_PARALLEL:
            runInParallel = True;
            if DEBUGGING: print("    >> Turning 'runInParallel' on because of '" + arg + "'");
        elif arg == "--help" or arg == "-h" or arg == "/?":
            printHelp();
            if DEBUGGING: print("    >> Emitted help message");
            exit(0);
        elif arg == "--":
            sliceFiles.extend(sys.argv[index+1:]);
            if DEBUGGING: print("    >> Entered argument mode at index '" + str(index) + "'. There were '" + str(len(sys.argv[index+1:])) + "' arguments left");
            break;
        elif arg.startswith("-"):
            print("ERROR: unknown option: '" + arg + "'");
            printHelp();
            exit(3);
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
        print("    >> backTrack = '" + str(backTrack) + "'");
        print("    >> catchup = '" + str(catchup) + "'");
        print("    >> sliceFiles = '" + str(sliceFiles) + "'");
        print("    >> projPath = '" + str(projPath) + "'");
        print("    >> compilersPath = '" + str(compilersPath) + "'");
        print("    >> runInParallel = '" + str(runInParallel) + "'");
        print();




    # Before we do anything else, make sure the user is VERY AWARE that this will clean and reset their repo...
    print();
    print("!!! ------------------------------------------------- !!!");
    print("!!! BE WARNED THIS SCRIPT WILL CLEAN THE CURRENT REPO !!!");
    print("!!! DO NOT RUN THIS IF YOU HAVE ANY UNSAVED WORK LEFT !!!");
    print("!!! ------------------------------------------------- !!!");
    input("Press Enter to continue...");
    print();




    #### ============================================ ####
    #### Compute Defaults for and Sanitize Parameters ####
    #### ============================================ ####

    # Find the root of the repository. This is also a test that git is usable in the current directory.
    REPO_ROOT = runCommand(["git", "rev-parse", "--show-toplevel"], None, checked=True, capture=True);
    if DEBUGGING: print("    >> REPO_ROOT = '" + str(REPO_ROOT) + "'");
    if not os.path.isdir(REPO_ROOT):
        print("ERROR: Expected repository root to be at '" + REPO_ROOT + "', but no such directory exists!");
        exit(11);

    # This is the path where we're going to store all the results.
    # We don't create it yet, just compute what the path is and store it.
    compareDir = os.path.join(REPO_ROOT, "_slice_compare_");

    # If we're going to be running the Slice compiler in parallel, we allocate a process pool to use for that.
    if runInParallel:
        EXECUTOR = concurrent.futures.ProcessPoolExecutor();
        if DEBUGGING: print("    >> Allocated a parallel executor with " + str(EXECUTOR._max_workers) + "processes");

    # Store which branch the repository is currently on, so we can switch back to it when we're done running.
    ORIGINAL_BRANCH = runCommand(["git", "rev-parse", "--abbrev-ref", "HEAD"], None, checked=True, capture=True);

    # If no compilers were specified, we want to run _all_ the compilers.
    if len(compilers) == 0:
        compilers = ["ice2slice", "slice2cpp", "slice2cs", "slice2java", "slice2js", "slice2matlab", "slice2php", "slice2py", "slice2rb", "slice2swift"];
        #TODO We don't build 'slice2swift' on windows... we should fix this in the future.
        if IS_WINDOWS:
            compilers.remove("slice2swift");
        #TODO 'ice2slice' hits an assertion when compiling constants. Unfortunately, not worth running yet.
        compilers.remove("ice2slice");
        if DEBUGGING: print("    >> No compilers were specified. Setting to '" + str(compilers) + "'");

    # Only one of these 'modes' can be used at a time: "specific branches", "back-tracking", and 'catch-up".
    # If any pair of these have been enabled by command-line input, we exit with an error.
    if (len(branches) != 0) and (backTrack != None):
        print("ERROR: you cannot specify branches and a back-track count at the same time");
        exit(12);
    if (len(branches) != 0) and (catchup != False):
        print("ERROR: you cannot specify branches and enable catch-up mode at the same time");
        exit(13);
    if (backTrack != None) and (catchup != False):
        print("ERROR: you cannot specify a back-track count and enable catch-up mode at the same time");
        exit(14);

    # If no branches were specified, and we aren't back-tracking or catching-up, we default to using the current branch.
    if len(branches) == 0 and backTrack == None and catchup == False:
        branches = [ORIGINAL_BRANCH];
        if DEBUGGING: print("    >> No branches were specified. Setting to current branch '" + str(branches[0]) + "'");

    # If we're 'catching-up', we re-use back-tracking by determining how many commits '_slice_compare_' is behind 'HEAD'.
    if catchup:
        if DEBUGGING: print("    > Catchup mode has been enabled. Determining how many commits to backtrack...");
        if not os.path.isdir(compareDir):
            print("Catchup mode was specified, but there was no pre-existing '_slice_compare_' repo to catch up!");
            exit(16);

        # Get the commit ID of the last commit that was compared with this script from the commit message.
        lastComparedCommitMessage = runCommand(["git", "-C", compareDir, "log", "--format=%B", "-n", "1"], None, checked=True, capture=True);
        idStart = lastComparedCommitMessage.index("zeroc-ice/ice@") + len("zeroc-ice/ice@");
        idEnd = lastComparedCommitMessage.index(')', idStart);
        lastComparedCommitId = lastComparedCommitMessage[idStart : idEnd];

        # Determine how many commits behind this is from the current repository's 'HEAD'.
        # Then we subtract '1', because backTrack always adds '1' because it wants to build the last commit.
        # But here, we've already done the 'last commit' we only want to do the commits that come after it.
        commitsBehind = runCommand(["git", "rev-list", "--count", lastComparedCommitId + ".."], None, checked=True, capture=True);
        backTrack = int(commitsBehind) - 1;
        if DEBUGGING: print("    > To catchup, we need to backtrack by '" + commitsBehind + "' commits");

    # If we're 'back-tracking', we re-use the 'branches' field by filling it with the last N commits.
    if backTrack != None:
        if DEBUGGING: print("    >> branches has been set to backtrack " + str(backTrack) + " times");
        backCommits = [("HEAD~" + str(i)) for i in range(backTrack + 1)];
        backCommits.reverse();
        for commit in backCommits:
            commitID = runCommand(["git", "rev-parse", commit], "git rev-parse <commit>", checked=True, capture=True);
            branches.append(commitID);

    # If no slice files were provided, we want to recursively get ALL the slice files in the current directory.
    if len(sliceFiles) == 0:
        sliceFiles = [CURRENT_DIR];
        if DEBUGGING: print("    >> No Slice files were specified. Setting to '" + str(CURRENT_DIR) + "'");

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

    def resolveSliceFiles(sliceFiles):
        # Check for any directories that were passed in as Slice files.
        # We recursively check each of these directories for Slice files and use those instead.
        resolvedSliceFiles = [];
        for file in sliceFiles:
            if os.path.isdir(file):
                globPattern = os.path.join(file, "**/*.ice");
                if DEBUGGING: print("    >> Encountered Slice directory of '" + file + "', globbing for '" + str(globPattern) + "'");
                resolvedSliceFiles.extend(glob.iglob(globPattern, recursive=True));
            else:
                resolvedSliceFiles.append(file);

        # After we know that we only have files left, we need to sanitize the Slice file paths.
        # We want forward slashes only, and to make sure that all the paths live in the repository.
        resolvedSliceFiles = [os.path.abspath(f).replace('\\', '/') for f in resolvedSliceFiles];
        sanitizedRepoRoot = REPO_ROOT.replace('\\', '/') + '/';
        if DEBUGGING: print("    >> 'sanitizedRepoRoot' = '" + str(sanitizedRepoRoot) + "'");
        for f in resolvedSliceFiles:
            if not f.startswith(sanitizedRepoRoot):
                print("ERROR: This script cannot be run on '" + f + "' since it lives outside of the repository.");
            if not os.path.exists(f):
                print("ERROR: The Slice file '" + f + "' does not exist on the current branch.");

        # Remove the REPO_ROOT from the slice Files, and filter out any files which live outside of the repository.
        resolvedSliceFiles = [f[len(sanitizedRepoRoot):] for f in resolvedSliceFiles if (f.startswith(sanitizedRepoRoot) and os.path.isfile(f))];
        if DEBUGGING:
            print();
            print("    >> resolvedSliceFiles = '" + str(resolvedSliceFiles) + "'");
            print();

        # TODO: delete this and add negative file searching or something!
        def removeStuff(file):
            if file.startswith("cpp/test/Slice"):
                return False;
            if file.startswith("java/test/Ice") or file.startswith("java-compat/test/Ice"):
                return False;
            return True;
        resolvedSliceFiles = list(filter(removeStuff, resolvedSliceFiles));

        print("    A total of " + str(len(resolvedSliceFiles)) + " Slice files will be compiled.");
        return resolvedSliceFiles;




    #### ================================= ####
    #### Let's Actually Do Some Stuff Now! ####
    #### ================================= ####

    # First, navigate to the repo root. It's easier if we're running in a known location.
    os.chdir(REPO_ROOT);

    # Then, do a preliminary clean and reset, to make sure we're in a known state.
    git_clean(True);
    git_reset();

    # Create a new directory that we'll use as scratch space for comparing the generated code.
    Path(compareDir).mkdir(parents=True, exist_ok=True);

    # Initialize a git repository in that directory. We utilize git to do the diffing for us!
    runCommand(["git", "-C", compareDir, "-c", "init.defaultBranch=master", "init"], "git -C ... init", checked=True, capture=False);
    runCommand(["git", "-C", compareDir, "config", "user.name", "temp"], "git -C ... config user.name ...", checked=True, capture=False);
    runCommand(["git", "-C", compareDir, "config", "user.email", "temp@zeroc.com"], "git -C ... config user.email ...", checked=True, capture=False);

    # Then, we want to compile the slice Files against each provided branch, and store them in this scratch git repository.
    try:
        for branch in branches:
            print();
            print("================================================================================");

            # Checkout the branch, and perform a clean build.
            git_checkout(branch);
            git_clean(False);

            # Get the current branch's name and the ID of the commit it's pointing at.
            branchName = runCommand(["git", "rev-parse", "--abbrev-ref", "HEAD"], None, checked=True, capture=True);
            branchID = runCommand(["git", "rev-parse", "--short", "HEAD"], None, checked=True, capture=True);

            # Create a directory to store the generated code in after we finish building the compilers in the next step.
            outputDirBase = os.path.join(REPO_ROOT, "_slice_gen_" + branchName + "_" + branchID);
            Path(outputDirBase).mkdir();

            # And also go ahead and resolve which Slice files we should compile from this branch.
            resolvedSliceFiles = resolveSliceFiles(sliceFiles);

            # Build the compilers so we can run them.
            outputString = "";
            try:
                print("Building '" + branchName + " @ " + branchID + "'...");
                if DEBUGGING: print("--------------------------------------------------------------------------------");
                build(compilers, projPath, pythonPath);
                if DEBUGGING: print("--------------------------------------------------------------------------------");
                print("Build complete!");

                # Run all the Slice compilers!
                for compiler in compilers:
                    compilerName = Path(compiler).stem;
                    print("    Running " + compilerName + "...");
                    compilerOutputDir = os.path.join(outputDirBase, compilerName);

                    # Ironically, we cannot run 'slice2py' in parallel, since multiple files read/write to a single "__init__.py" file.
                    # We also cannot run java or matlab, since they hit race conditions when generating directories.
                    if runInParallel and compilerName not in ["slice2py", "slice2java", "slice2matlab"]:
                        futures = [
                            EXECUTOR.submit(sliceCompile, compiler, "./" + file, os.path.join(compilerOutputDir, os.path.dirname(file)))
                            for file in resolvedSliceFiles
                        ];
                        for future in futures:
                            result = future.result();
                            outputString += result;
                            print(result, end='');
                    else:
                        for file in resolvedSliceFiles:
                            outputDir = os.path.join(compilerOutputDir, os.path.dirname(file));
                            result = sliceCompile(compiler, "./" + file, outputDir);
                            outputString += result;
                            print(result, end='');

                print("    Storing generated code...");
            except subprocess.CalledProcessError as ex:
                print("!!!! BUILD FAILURE !!!!")
                print();
                print("Skipping code generation phase and moving to the next branch...")
                outputString += "\n!!!!!!!!!!!!!!!!!!!!!!!\n!!!! BUILD FAILURE !!!!\n!!!!!!!!!!!!!!!!!!!!!!!\n" + traceback.format_exc().strip();

            # If there were any diagnostics produced during the build/code-gen phases, write them into the "DIAGNOSTICS" file.
            with open(os.path.join(outputDirBase, "DIAGNOSTICS"), "w") as errorFile:
                errorFile.write(outputString.replace(REPO_ROOT, "REPO_ROOT"));

            # Now that we've generated all the code we care about into this '_slice_gen_*' folder,
            # We rip out the core '.git' folder from our scratch repo, and move into this '_slice_gen_*' folder.
            moveDir(os.path.join(compareDir, ".git"), outputDirBase);

            # Check if there's been any changes to the generated code. If there have been, we want to add and commit them.
            # We have this check because if there are no changes, `git commit` 'fails' with a non-zero exit code.
            result = runCommand(["git", "-C", outputDirBase, "status", "-s"], "git -C ... status -s", checked=True, capture=True);
            if result != "":
                # Grab various information from whichever commit we just built everything off of.
                # We want to include this information (message, date, author) in the commits we generate in the scratch repo.
                commitMessage = runCommand(["git", "log", "--format=%B", "-n", "1"], None, checked=True, capture=True);
                if DEBUGGING: print("    >> RESULT 'retrieved commit message of '" + commitMessage + "'");
                commitAuthor = runCommand(["git", "log", "--format=%an <%ae>", "-n", "1"], None, checked=True, capture=True);
                if DEBUGGING: print("    >> RESULT 'retrieved commit author of '" + commitAuthor + "'");
                commitDate = runCommand(["git", "log", "--format=%ad", "-n", "1"], None, checked=True, capture=True);
                if DEBUGGING: print("    >> RESULT 'retrieved commit timestamp of '" + commitDate + "'");

                # Construct a new commit message, which contains the message of the original commit (but with any '#' links sanitized),
                # and with a little header that says which branch and commit the generated code was built off of, with a link to it.
                message = branchName + ":(zeroc-ice/ice@" + branchID + ") " + commitMessage.replace("#", "zeroc-ice/ice#");

                # We commit the contents of this '_slice_gen_*' folder, so that the '.git' will capture it.
                ENVIRONMENT["GIT_COMMITTER_DATE"] = commitDate;
                ENVIRONMENT["GIT_AUTHOR_DATE"] = commitDate;
                runCommand(["git", "-C", outputDirBase, "add", "--all"], "git -C ... add --all", checked=True, capture=False);
                runCommand(["git", "-C", outputDirBase, "commit", "--author=" + commitAuthor, "-m", message], "git -C ... commit ...", checked=True, capture=False);
                del ENVIRONMENT["GIT_COMMITTER_DATE"];
                del ENVIRONMENT["GIT_AUTHOR_DATE"];

            # Now that we've captured any changes in the generated code, move the '.git' back to where it belongs,
            moveDir(os.path.join(outputDirBase, ".git"), compareDir);

            # We're done with this branch!
            print("Finished!");
            print("================================================================================");
            if backTrack != None:
                print("Backtrack iterations remaining: '" + str(backTrack) + "'");
                backTrack -= 1;

                # Check if enough cycles have passed yet to warrant a repack of the scratch repository.
                # The `+2` is because we don't want to repack at `backTrack==0`, since we already repack at the end of the script.
                if ((backTrack+2) % REPACK_COUNTER_MAX == 0):
                    git_repack(compareDir);

        # Finally, we do a hard reset on our now fully completed scratch git repository,
        # so that it doesn't look like all it's files were deleted when you interact with it.
        runCommand(["git", "-C", compareDir, "reset", "--hard"], "git -C ... reset --hard", checked=True, capture=False);
        # And do a final packing/garbage collection pass to keep file sizes down.
        git_repack(compareDir);

        print();
        print("The results of this script have been stored in the '" + compareDir + "' directory.");
        print();

        # Okay, now the actual last step, we do a final clean to remove everything except the new git repository we created,
        # And switch back to the branch that this repository was on originally, to minimize inconvenience for users.
        if DEBUGGING: print("    >> Running final cleanup logic now");
        git_clean(False);
        git_checkout(ORIGINAL_BRANCH);
    except KeyboardInterrupt:
        # If the script was cancelled, and we're not trying to debug it, cleanup what we were doing before exiting.
        if not DEBUGGING:
            print("Cancellation requested: performing a quick cleanup (takes around 1 second)")
            time.sleep(0.5);
            if outputDirBase:
                tempGitPath = os.path.join(outputDirBase, ".git");
                if os.path.exists(tempGitPath):
                    moveDir(tempGitPath, compareDir);
            git_clean(False);
            git_checkout(ORIGINAL_BRANCH);

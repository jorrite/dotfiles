# A repo is only known to herdr-projects once a task is added against it.
# Restarts the Coordinator afterward so its sandbox picks up the newly-
# mounted repo (cs-launch mounts every repo in repos.json at Coordinator
# launch, not dynamically).
function hpa
    if test -z "$argv[1]"
        echo "usage: hpa <name> [path]" >&2
        return 1
    end
    set -l name $argv[1]
    set -l path $argv[2]
    if test -n "$path"
        herdr-projects add "$name" --repo $path
    else
        herdr-projects add "$name"
    end
    herdr-projects coordinator restart
end

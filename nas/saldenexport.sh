#!/bin/sh
# To run from the NAS scheduler. XLSX data never goes through the web API.
set -eu
umask 077

usage() {
    echo "Aufruf: $0 export {synology|qnap} COMPOSE-VERZEICHNIS [DOCKER] [COMPOSE-PROJEKT]" >&2
    echo "        $0 cleanup {synology|qnap}" >&2
    exit 2
}

[ "$#" -ge 2 ] || usage
case "$2" in
    synology) target=/volume1/kostbar-backup ;;
    qnap) target=/share/kostbar-backup ;;
    *) usage ;;
esac
[ -d "$target" ] || { echo "Saldenexport-Verzeichnis fehlt: $target" >&2; exit 1; }

case "$1" in
    export)
        [ "$#" -ge 3 ] && [ "$#" -le 5 ] || usage
        compose_dir=$3
        docker=${4:-docker}
        project=${5:-kostbar}
        export TZ=Europe/Berlin
        output="$target/KoSTbar-Salden-$(date '+%Y-%m-%d').xlsx"
        if [ -f "$output" ]; then
            echo "Saldenexport bereits vorhanden: $output"
            exit 0
        fi
        [ ! -e "$output" ] || { echo "Ungültiges Exportziel: $output" >&2; exit 1; }
        cd "$compose_dir"
        tmp=$(mktemp "$target/.kostbar-salden-XXXXXXXX")
        trap 'rm -f "$tmp"' EXIT
        trap 'exit 1' HUP INT TERM
        "$docker" compose -p "$project" exec -T app python server.py export-balances > "$tmp"
        [ -s "$tmp" ] || { echo "KoSTbar hat keine Arbeitsmappe geliefert." >&2; exit 1; }
        # Both files are on the same volume. Publishing by hard link is atomic
        # and never replaces a valid daily file from another invocation.
        if ! ln "$tmp" "$output"; then
            [ -f "$output" ] || exit 1
        fi
        printf 'Saldenexport erstellt: %s\n' "$output"
        ;;
    cleanup)
        [ "$#" -eq 2 ] || usage
        find "$target/" -maxdepth 1 -type f -name 'KoSTbar-Salden-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].xlsx' \
            -mtime +89 -exec rm -f {} \;
        ;;
    *) usage ;;
esac

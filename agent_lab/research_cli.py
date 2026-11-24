"""Installed research-library command dispatcher, with no eager model imports."""
import sys


def main(argv=None, *, embedding_observer=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ['-h', '--help']:
        print('agentlab-research {prepare,check-model,ingest,search,read,serve} [options]\n'
              'Use COMMAND --help for options. Local UTF-8 sources; CPU E5; exact version citations.')
        return
    if args[0] in ['prepare', 'check-model']:
        from .research_intake import main as command
        return command(args)
    if args[0] == 'serve':
        from .research_mcp import main as command
        return command(args[1:], embedding_observer=embedding_observer)
    if args[0] in ['ingest', 'search', 'read']:
        from .research_library import main as command
        return command(args, embedding_observer=embedding_observer)
    raise SystemExit('Unknown command: '+args[0])


if __name__ == '__main__': main()

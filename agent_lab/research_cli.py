"""Installed research-library command dispatcher, with no eager model imports."""
import sys


def main(argv=None, *, embedding_observer=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ['-h', '--help']:
        print('agentlab-research {prepare,prepare-pdf,check-model,ingest,search,search-batch,batch-status,read,serve} [options]\n'
              'Use COMMAND --help for options. Local UTF-8/PDF page sources; CPU E5; exact version citations.')
        return
    if args[0] == 'batch-status':
        from .research_jobs import main as command
        return command(args[1:])
    if args[0] == 'prepare-pdf':
        from .research_pdf import main as command
        return command(args[1:])
    if args[0] in ['prepare', 'check-model']:
        from .research_intake import main as command
        return command(args)
    if args[0] == 'serve':
        from .research_mcp import main as command
        return command(args[1:], embedding_observer=embedding_observer)
    if args[0] in ['ingest', 'search', 'search-batch', 'read']:
        from .research_library import main as command
        return command(args, embedding_observer=embedding_observer)
    raise SystemExit('Unknown command: '+args[0])


if __name__ == '__main__': main()

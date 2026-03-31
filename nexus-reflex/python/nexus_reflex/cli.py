import sys
import json
import nexus_reflex as nexus

def main():
    args = sys.argv[1:]
    
    if len(args) == 0:
        print("Usage: nexus-reflex <path> or nexus-reflex --action '<json>'")
        sys.exit(1)

    if args[0] == "--action":
        if len(args) < 2:
            print("Error: Missing action JSON")
            sys.exit(1)
        res = nexus.apply_action(args[1])
        if res: print(res)
    else:
        tree = nexus.scan(args[0])
        if tree:
            print(json.dumps(tree, indent=2))

if __name__ == "__main__":
    main()

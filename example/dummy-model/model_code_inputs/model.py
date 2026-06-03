"""Fictional 2-D Rayleigh-Bénard convection driver (demo only — does nothing real)."""
import argparse
import yaml


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params.yaml")
    args = ap.parse_args()
    params = yaml.safe_load(open(args.params))
    print(f"Pretending to run convection at Ra={params['rayleigh_number']} "
          f"on a {params['resolution']}x{params['resolution']} mesh...")


if __name__ == "__main__":
    main()

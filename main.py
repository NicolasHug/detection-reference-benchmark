import contextlib
import itertools
import pathlib
import string
import sys
from datetime import datetime

import tabulate

import torch
from torch.hub import tqdm
from torch.utils.collect_env import main as collect_env

import torchvision

torchvision.disable_beta_transforms_warning()

from tasks import make_task
from transforms import classification_complex_pipeline_builder, classification_simple_pipeline_builder
from datasets import classification_dataset_builder, detection_dataset_builder


class Tee:
    def __init__(self, stdout, root=pathlib.Path(__file__).parent / "results"):
        self.stdout = stdout
        self.root = root
        self.file = open(root / f"{datetime.utcnow():%Y%m%d%H%M%S}.log", "w")

    def write(self, message):
        self.stdout.write(message)
        self.file.write(message)

    def flush(self):
        self.stdout.flush()
        self.file.flush()


def main(*, input_types, tasks, num_samples):
    # This is hardcoded when using a DataLoader with multiple workers:
    # https://github.com/pytorch/pytorch/blob/19162083f8831be87be01bb84f186310cad1d348/torch/utils/data/_utils/worker.py#L222
    torch.set_num_threads(1)

    dataset_rng = torch.Generator()
    dataset_rng.manual_seed(0)
    dataset_rng_state = dataset_rng.get_state()

    for (task_name, pipeline_builder, dataset_builder, pipeline_builder_kwargs)  in tasks:
        print("#" * 60)
        print(task_name)
        print("#" * 60)

        totals = {}
        # for input_type, api_version in itertools.product(input_types, ["v1", "v2"]):
        for input_type, api_version in itertools.product(input_types, ["v2", "v1"]):
            if input_type == "PIL" and api_version == "v2":
                continue
            dataset_rng.set_state(dataset_rng_state)
            task = make_task(
                # task_name,
                pipeline_builder,
                dataset_builder,
                input_type=input_type,
                api_version=api_version,
                dataset_rng=dataset_rng,
                num_samples=num_samples,
                pipeline_builder_kwargs=pipeline_builder_kwargs,
            )
            if task is None:
                continue

            print(f"{input_type=}, {api_version=}")
            print()

            pipeline, dataset = task

            # warm up, to avoid including torch.compile times
            for sample in dataset[:10]:
                pipeline(sample)
            pipeline.reset_times()

            torch.manual_seed(0)
            for sample in tqdm(dataset):
                pipeline(sample)

            results = {
                transform_name: times.mul(1e6)
                for transform_name, times in pipeline.extract_times().items()
            }
            table, total = make_pipeline_stats(results)
            print(table)
            print()
            print(f"Results computed for {num_samples:_} samples and reported in µs")
            print("-" * 60)

            totals[(input_type, api_version)] = total

        print("Summary")
        print()
        print(make_summary_stats(totals))
        print()
        print("Slowdown computed as row / column")


def make_pipeline_stats(results):
    def make_row(times):
        # min, max = map(float, times.aminmax())
        # q25, median, q75 = times.quantile(times.new_tensor([0.25, 0.5, 0.75])).tolist()
        # return [min, q25, median, q75, max]
        median = torch.median(times)
        return [median]

    # headers = ["transform", "min", "25% quantile", "median", "75% quantile", "max"]
    headers = ["transform", "median"]
    data = [
        [transform_name, *make_row(times)] for transform_name, times in results.items()
    ]

    total_times = torch.stack(list(results.values())).sum(dim=0)
    total_row = make_row(total_times)
    # total_median = total_row[2]
    total_median = total_row[0]
    data.extend([tabulate.SEPARATING_LINE, ["Total", *total_row]])

    table = tabulate.tabulate(data, headers=headers, tablefmt="simple", floatfmt=".0f")

    return table, total_median


def make_summary_stats(totals):
    keys, values = zip(*totals.items())

    row_labels = [
        f"{', '.join(key)}  [{id}]" for key, id in zip(keys, string.ascii_lowercase)
    ]
    headers = ["", *(f"[{id}]" for id in string.ascii_lowercase[: len(row_labels)])]

    slowdowns = torch.tensor(values, dtype=torch.float64).unsqueeze(1)
    slowdowns = slowdowns / slowdowns.T

    data = [[row_label, *bar] for row_label, bar in zip(row_labels, slowdowns.tolist())]

    return tabulate.tabulate(
        data, headers=headers, tablefmt="simple", floatfmt=".2f", stralign="right"
    )


if __name__ == "__main__":
    tee = Tee(stdout=sys.stdout)

    with contextlib.redirect_stdout(tee):
        main(
            tasks=[
                ("Classif simple", classification_simple_pipeline_builder, classification_dataset_builder, {}),
                ("Classif simple, CL-Normalize", classification_simple_pipeline_builder, classification_dataset_builder, {"normalize_input": "CL"}),
                ("Classif simple, CF-Normalize", classification_simple_pipeline_builder, classification_dataset_builder, {"normalize_input": "CF"}),
                ("Classif simple, compiled-Normalize", classification_simple_pipeline_builder, classification_dataset_builder, {"normalize_input": "compile"}),
                ("Classif complex", classification_complex_pipeline_builder, classification_dataset_builder, {}),
                ("Classif complex, CL-Normalize", classification_complex_pipeline_builder, classification_dataset_builder, {"normalize_input": "CL"}),
                ("Classif complex, CF-Normalize", classification_complex_pipeline_builder, classification_dataset_builder, {"normalize_input": "CF"}),
                ("Classif complex, compiled-Normalize", classification_complex_pipeline_builder, classification_dataset_builder, {"normalize_input": "compile"}),
                # "detection-ssdlite",
            ],
            # input_types=["Tensor", "PIL", "Datapoint"],
            input_types=["Tensor", "PIL"],
            # input_types=["Tensor"],
            num_samples=1_000,
            # num_samples=10,
        )

        print("#" * 60)
        # collect_env()

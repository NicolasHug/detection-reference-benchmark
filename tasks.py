from datasets import classification_dataset_builder, detection_dataset_builder
from transforms import (
    classification_complex_pipeline_builder,
    classification_simple_pipeline_builder,
    detection_ssdlite_pipeline_builder,
)

# TASKS = {
#     "classification-simple": (
#         classification_simple_pipeline_builder,
#         classification_dataset_builder,
#     ),
#     "classification-complex": (
#         classification_complex_pipeline_builder,
#         classification_dataset_builder,
#     ),
#     "detection-ssdlite": (
#         detection_ssdlite_pipeline_builder,
#         detection_dataset_builder,
#     ),
# }


# def make_task(name, *, input_type, api_version, dataset_rng, num_samples):
def make_task(pipeline_builder, dataset_builder, *, input_type, api_version, dataset_rng, num_samples, pipeline_builder_kwargs={}):
    # pipeline_builder, dataset_builder = TASKS[name]

    pipeline = pipeline_builder(input_type=input_type, api_version=api_version, **pipeline_builder_kwargs)
    if pipeline is None:
        return None

    dataset = dataset_builder(
        api_version=api_version,
        rng=dataset_rng,
        num_samples=num_samples,
    )

    return pipeline, dataset

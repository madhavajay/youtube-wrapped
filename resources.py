from pathlib import Path

import yaml


def ensure_syft_yaml(client):
    syft_yaml_path = client.datasite_path / "public" / "syft.yaml"

    syft_data = {
        "schema": "org.openmined.syft.index:1.0.0",
        "email": client.email,
        "resources": [
            {
                "name": "datasets",
                "path": "./resources/datasets.yaml",
                "schema": "org.openmined.syft.datasets:1.0.0",
            }
        ],
    }

    if syft_yaml_path.exists():
        with syft_yaml_path.open("r", encoding="utf-8") as file:
            existing_data = yaml.safe_load(file) or {}

        # Update only missing keys
        for key, value in syft_data.items():
            if key not in existing_data:
                existing_data[key] = value

        syft_data = existing_data

    resources_path = client.datasite_path / "public" / "resources"
    client.makedirs(resources_path)

    with syft_yaml_path.open("w", encoding="utf-8") as file:
        file.write("---\n")  # Add the YAML document start marker
        yaml.dump(syft_data, file, default_flow_style=False)

    datasets_yaml_path = client.datasite_path / "public" / "resources" / "datasets.yaml"
    datasets_data = {"schema": "org.openmined.syft.datasets:1.0.0", "resources": []}
    if not datasets_yaml_path.exists():
        with datasets_yaml_path.open("w", encoding="utf-8") as file:
            file.write("---\n")  # Add the YAML document start marker
            yaml.dump(datasets_data, file, default_flow_style=False)


def add_dataset(client, dataset_name, syft_uri, private_path, schema_name):
    schema = load_schema(schema_name)
    schemas_path = client.datasite_path / "public" / "resources" / "schemas"
    client.makedirs(schemas_path)

    datasets_yaml_path = client.datasite_path / "public" / "resources" / "datasets.yaml"
    datasets_data = {"schema": "org.openmined.syft.datasets:1.0.0", "resources": []}

    if datasets_yaml_path.exists():
        with datasets_yaml_path.open("r", encoding="utf-8") as file:
            loaded = yaml.safe_load(file) or {}
            # Merge in a way that ensures required keys
            datasets_data.update(
                {k: loaded.get(k, v) for k, v in datasets_data.items()}
            )
            # Also keep any unexpected extra keys
            for k in loaded:
                if k not in datasets_data:
                    datasets_data[k] = loaded[k]

    # Extract schema name and fields
    schema_fields = {k: v for k, v in schema.items()}

    # Save the schema to a file
    schema_file_path = schemas_path / f"{schema_name.replace(':', '_')}.yaml"
    with schema_file_path.open("w", encoding="utf-8") as schema_file:
        schema_file.write("---\n")  # Add the YAML document start marker
        yaml.dump(schema_fields, schema_file, default_flow_style=False)

    # Add or update the dataset in the resources
    new_resource = {
        "name": dataset_name,
        "path": str(syft_uri),
        "schema": schema_name,
        "schema_ref": f"./resources/schemas/{schema_name.replace(':', '_')}.yaml",
    }

    # Check if a resource with the same name already exists
    existing_resource = next(
        (res for res in datasets_data["resources"] if res["name"] == dataset_name), None
    )

    if existing_resource:
        # Overwrite the existing resource
        existing_resource.update(new_resource)
    else:
        # Add the new resource if it doesn't exist
        datasets_data["resources"].append(new_resource)

    with datasets_yaml_path.open("w", encoding="utf-8") as file:
        file.write("---\n")  # Add the YAML document start marker
        yaml.dump(datasets_data, file, default_flow_style=False)

    mapping_file_path = Path.home() / ".syftbox" / "mapping.yaml"

    # Ensure the parent directory exists
    if not mapping_file_path.parent.exists():
        mapping_file_path.parent.mkdir(parents=True, exist_ok=True)

    mapping_data = {}

    # Check if the mapping file exists and load its content
    if mapping_file_path.exists():
        with mapping_file_path.open("r", encoding="utf-8") as file:
            mapping_data = yaml.safe_load(file) or {}

    # Update the mapping data with the new syft_uri and private_path
    mapping_data[syft_uri] = str(private_path)

    # Write the updated mapping data back to the file with the YAML document start marker
    with mapping_file_path.open("w", encoding="utf-8") as file:
        file.write("---\n")  # Add the YAML document start marker
        yaml.dump(mapping_data, file, default_flow_style=False)


def load_schema(schema_name):
    current_dir = Path(__file__).parent
    schema_file_path = current_dir / "schemas" / f"{schema_name.replace(':', '_')}.yaml"
    with open(schema_file_path, "r", encoding="utf-8") as file:
        schema = yaml.safe_load(file)
    return schema

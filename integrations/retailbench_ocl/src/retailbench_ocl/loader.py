"""Load a small but real RetailBench environment from an external checkout."""

from __future__ import annotations

from contextlib import contextmanager
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Iterator


MINIMAL_SKU = "3828111129"
MINIMAL_CATEGORY = "Bathroom_Tissues"
SMALL_SKUS = (MINIMAL_SKU, "3700060511", "4200013000")


class RetailBenchLoadError(RuntimeError):
    """Raised when the external RetailBench checkout cannot be loaded."""


@contextmanager
def load_minimal_environment(retailbench_root: str | Path) -> Iterator[Any]:
    """Yield RetailBench configured with one real SKU and real supplier data.

    RetailBench stays external. The temporary slice only removes unrelated SKUs
    so this integration smoke test completes quickly and deterministically.
    """
    with load_small_environment(retailbench_root, sku_ids=(MINIMAL_SKU,)) as environment:
        yield environment


@contextmanager
def load_small_environment(
    retailbench_root: str | Path,
    *,
    sku_ids: tuple[str, ...] = SMALL_SKUS,
    random_seed: int | None = None,
) -> Iterator[Any]:
    """Yield a real RetailBench environment restricted to a few public SKUs."""
    if not sku_ids or any(not isinstance(item, str) or not item.strip() for item in sku_ids):
        raise RetailBenchLoadError("sku_ids must contain one or more non-empty strings")
    if len(set(sku_ids)) != len(sku_ids):
        raise RetailBenchLoadError("sku_ids must be unique")

    root = Path(retailbench_root).expanduser().resolve()
    _validate_checkout(root)

    with tempfile.TemporaryDirectory(prefix="retailbench-ocl-") as temp_name:
        temp_root = Path(temp_name)
        data_dir = _prepare_small_data(root, temp_root, sku_ids)
        module = _import_retailbench(root)
        config_module = importlib.import_module("util.default_config")
        config = config_module.create_dynamic_middle_config()
        config.update(
            {
                "debug": False,
                "data_dir": str(data_dir),
                "customer_data_path": str(root / "data/dynamic/customer_number"),
                "init_sql_path": None,
                "order_record_dir": str(temp_root / "records"),
                "log_dir": str(temp_root / "logs"),
                "enable_review": False,
                "enable_new": False,
                "selected_categories": [MINIMAL_CATEGORY],
                "sku_ids": list(sku_ids),
                "global_random_seed": random_seed,
            }
        )
        if random_seed is not None:
            try:
                import numpy as np

                np.random.seed(random_seed)
            except ImportError:
                pass
        yield module.RetailEnvironment(config)


def _validate_checkout(root: Path) -> None:
    required = (
        root / "retail_environment.py",
        root / "module/sku.py",
        root / "model/return_rate_model.py",
        root / "data/dynamic/customer_number/15/data.json",
        root / "data/dynamic/simulate_data/15/sku_model_parameter.json",
        root / "data/dynamic/simulate_data/15/upc.json",
        root
        / "data/dynamic/simulate_data/15"
        / MINIMAL_CATEGORY
        / f"{MINIMAL_SKU}_suppliers.json",
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RetailBenchLoadError(
            "RetailBench checkout is incomplete; missing: " + ", ".join(missing)
        )


def _prepare_small_data(
    root: Path,
    temp_root: Path,
    sku_ids: tuple[str, ...],
) -> Path:
    source = root / "data/dynamic/simulate_data/15"
    target_root = temp_root / "simulate_data"
    target = target_root / "15"
    category_dir = target / MINIMAL_CATEGORY
    category_dir.mkdir(parents=True)

    params = json.loads((source / "sku_model_parameter.json").read_text(encoding="utf-8"))
    upc = json.loads((source / "upc.json").read_text(encoding="utf-8"))
    missing_params = [sku_id for sku_id in sku_ids if sku_id not in params]
    if missing_params:
        raise RetailBenchLoadError(
            "Selected SKUs are absent upstream: " + ", ".join(missing_params)
        )
    selected_ids = set(sku_ids)
    selected_upc = [item for item in upc if str(item.get("UPC")) in selected_ids]
    found_ids = {str(item.get("UPC")) for item in selected_upc}
    missing_upc = [sku_id for sku_id in sku_ids if sku_id not in found_ids]
    if missing_upc:
        raise RetailBenchLoadError(
            "UPC metadata is absent for: " + ", ".join(missing_upc)
        )

    (target / "sku_model_parameter.json").write_text(
        json.dumps({sku_id: params[sku_id] for sku_id in sku_ids}), encoding="utf-8"
    )
    (target / "upc.json").write_text(json.dumps(selected_upc), encoding="utf-8")
    for sku_id in sku_ids:
        supplier_path = source / MINIMAL_CATEGORY / f"{sku_id}_suppliers.json"
        if not supplier_path.exists():
            raise RetailBenchLoadError(f"Supplier metadata is absent for: {sku_id}")
        shutil.copy2(supplier_path, category_dir / supplier_path.name)
    return target_root


def _import_retailbench(root: Path) -> Any:
    if sys.version_info < (3, 10):
        raise RetailBenchLoadError(
            "RetailBench requires Python 3.10+; run this command with `python`, "
            "not macOS `/usr/bin/python3` when it is Python 3.9."
        )
    # Current upstream has one unqualified `from sku import ...`; adding both
    # paths supports it without patching or vendoring RetailBench.
    for path in (root, root / "module"):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    os.environ.setdefault("MPLCONFIGDIR", tempfile.gettempdir())
    os.environ.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())
    try:
        return importlib.import_module("retail_environment")
    except Exception as exc:
        raise RetailBenchLoadError(
            f"Could not import RetailBench from {root}: {type(exc).__name__}: {exc}"
        ) from exc

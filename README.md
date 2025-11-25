# SpatialDise

SpatialDise 是本项目中负责“空间推理题目生成”的核心 Python 包，包含从几何场景构建到图像渲染的一整套脚本与工具。它主要面向如下用例：

- 在 Blender 中批量生成空间推理题目（如 3D 旋转、折叠、组合、投影等）及对应的元数据；
- 作为上层生成 pipeline（例如 `scripts/main_pipeline.py` 或外部训练/评测脚本）的后端组件；
- 为其它工具脚本（如标注工具、可视化脚本）提供统一的数据与目录结构。

## 目录结构概览

- `SpatialDise/assets/`  
  存放生成器使用的静态资源，例如 Lucide 图标缓存等。

- `SpatialDise/generator/`  
  核心题目生成逻辑所在目录，内部包含：
  - `core/`：通用基础组件（相机/场景配置、几何与投影工具、日志与路径管理、Lucide 图标与材质 helper 等）；
  - `tasks/`：按题型划分的具体生成器实现（例如 `tasks/3d/3d_folding.py`、`tasks/3d/3d_rotation.py` 等），每个任务通常暴露一个 `*Generator` 类；
  - `scripts/`：与生成相关的命令行脚本（例如预缓存图标、批量生成数据集等）；
  - `tests/`：针对生成器行为的轻量级回归/一致性测试。

- `SpatialDise/tools/`  
  与 SpatialDise 数据/元数据交互的辅助工具模块（如可视化、评估或标注相关工具），通常在上层脚本中被调用。

## 使用方式（简要）

在上层代码中，一般通过注册表或直接导入的方式使用 SpatialDise 生成器，例如：

```python
from SpatialDise.generator.tasks import get_generator_class

GeneratorCls = get_generator_class("3d_folding")
gen = GeneratorCls(output_dir="output/box_folding", config={"num_questions": 10})
files, summary = gen.generate_dataset()
```

对于每个任务，`config` 字典通常至少包含：

- `num_questions`：生成题目的数量；
- `image_resolution`：渲染图像分辨率（如 `(640, 480)`）；
- `difficulty`：难度标签（如 `"easy"`, `"medium"`, `"hard"`）；
- 以及若干与方块数量、干扰项强度、是否使用长方体等相关的可选超参数。

## Python 环境（使用 uv）

SpatialDise 的大部分生成逻辑需要在 Blender 的 Python 环境中运行（依赖 `bpy`），但也有一些纯 Python 脚本（如配置管理、图标缓存等）可以在独立环境中运行。项目根目录下提供了 `pyproject.toml`，推荐使用 [uv](https://github.com/astral-sh/uv) 管理这些 Python 依赖：

1. 安装 uv（参考官方文档），然后在 SpatialDise 目录中创建/激活虚拟环境：

```bash
cd /path/to/SpatialDise
uv venv .venv
source .venv/bin/activate  # Windows 下使用 .venv\\Scripts\\activate
```

2. 根据当前目录下的 `pyproject.toml` 安装依赖并生成 `uv.lock`：

```bash
uv sync
```

这一步会解析 `pyproject.toml` 中的依赖（例如 `pyyaml`、`cairosvg` 等），创建或更新 `uv.lock` 并安装到当前虚拟环境。

3. 在 uv 环境中运行纯 Python 脚本，例如预缓存 Lucide 图标（无需 Blender）：

```bash
uv run SpatialDise/generator/scripts/cache_lucide_icons.py -- --icons circle square triangle
```

4. 如果希望在 Blender 中也使用这些库，需要将相同依赖安装到 Blender 自带的 Python 解释器中（方式视本地 Blender 安装而定，通常是调用 `blender --python -m pip install ...`）。

## Blender 安装与集成

SpatialDise 的 3D 题目生成依赖 Blender 提供的 `bpy` 与渲染能力。典型安装与集成方式如下：

1. 安装 Blender  
   - 从官方站点下载适合操作系统的版本：https://www.blender.org/download/  
   - 推荐使用 Blender 3.6 或更新版本（内置 Python 版本通常 ≥3.10，可与本项目依赖兼容）。

2. 验证 Blender 可用  
   安装后，在终端/命令行中运行：

   ```bash
   blender --version
   ```

   能看到版本信息即表示安装成功，并且 `blender` 已在 PATH 中。

3. 给 Blender 的 Python 安装额外依赖（可选）  
   如果希望在 Blender 中也使用 `pyyaml`、`cairosvg` 等库，可以执行：

   ```bash
   blender --background --python-expr "import sys; print(sys.executable)"
   ```

   根据输出的 Python 路径，用对应解释器安装依赖（示例）：

   ```bash
   /path/to/blender/python/bin/python3.10 -m pip install pyyaml cairosvg
   ```

4. 在 Blender 中运行 SpatialDise 生成脚本  
   例如，基于 YAML 配置一键生成 3D 题目：

   ```bash
   cd /path/to/SpatialDise
   blender --background --python SpatialDise/generator/cli/config_generate.py -- \
     --config configs/spatialdise_3d.yaml
   ```

   其中 `--` 之后的参数会传给 `config_generate.py`，该脚本会读取配置、调用各任务的生成器并将图像与元数据写入指定输出目录。

## 基于配置文件的一键生成

在 Blender 中，可以使用 `SpatialDise/generator/cli/config_generate.py` 通过 YAML/JSON 配置文件一键生成多个任务的数据集。例如：

```bash
blender --background --python SpatialDise/generator/cli/config_generate.py -- \
  --config configs/spatialdise_3d.yaml
```

示例 `configs/spatialdise_3d.yaml` 内容（YAML）：

```yaml
defaults:
  image_resolution: [640, 480]
  num_questions: 50
  use_gpu: true

tasks:
  - task: 3d_folding
    output_dir: blender_dataset/box_folding
    difficulty: medium    # 枚举难度（用于折叠/形状识别）

  - task: 3d_rotation
    output_dir: blender_dataset/3d_rotation
    num_questions: 100
    difficulty: hard
```

说明：
- 顶层的 `defaults` 会合并进每个 `tasks` 条目，可在条目内覆盖；
- 每个任务至少需要 `task` 字段（例如 `"3d_folding"`、`"3d_rotation"` 等），`output_dir` 省略时会使用按任务命名的默认目录；
- 推荐只使用 `difficulty` 这一套难度参数；如需更细粒度控制，可以在各任务条目中显式设置 `num_cells_min`、`num_cells_max`、`distractor_difficulty` 等字段。

## 难度预设与可自定义选项

SpatialDise 中的难度主要通过 `config["difficulty"]` 控制，部分任务还会推导出方块个数和干扰强度。默认（未覆盖时）的预设行为如下：

- `3d_rotation`（`SpatialDise/generator/tasks/3d/3d_rotation.py`）
  - easy：`num_cells_min=3`，`num_cells_max=5`
  - medium：`num_cells_min=5`，`num_cells_max=8`
  - hard：`num_cells_min=8`，`num_cells_max=12`

- `3d_combination`（`SpatialDise/generator/tasks/3d/3d_combination.py`）
  - easy：`num_cells_min=3`，`num_cells_max=5`
  - medium：`num_cells_min=5`，`num_cells_max=8`
  - hard：`num_cells_min=8`，`num_cells_max=12`

- `3d_projection`（视图匹配，`SpatialDise/generator/tasks/3d/3d_projection.py`）
  - easy：`num_cells_min=3`，`num_cells_max=5`，`distractor_difficulty=0.2`
  - medium：`num_cells_min=5`，`num_cells_max=8`，`distractor_difficulty=0.5`
  - hard：`num_cells_min=8`，`num_cells_max=12`，`distractor_difficulty=0.8`

- `3d_folding`（盒子折叠，`SpatialDise/generator/tasks/3d/3d_folding.py`）
  - `difficulty` 不直接改数值参数，而是控制干扰项策略：
    - easy：更倾向于修改单一可见面，变化明显（更换图标/颜色为主）；
    - medium：更频繁地在可见面与部分不太显眼的面上做旋转、镜像、替换等组合修改；
    - hard：可能修改多个面，并使用更细微的旋转/翻转组合，但仍保证从题目视角可区分。

- `3d_shape_finding`（找蓝面，`SpatialDise/generator/tasks/3d/3d_shape_finding.py`）
  - 默认 `difficulty="medium"`，`ortho_scale=5.0`；
  - `difficulty` 控制视角挑选和蓝面选择规则：
    - easy：三个视角差异更大，优先避免只看顶部，蓝面通常在前两视图出现次数较多且非顶面；
    - medium：视角间重叠更多，第三视图有适度随机旋转，蓝面选择更加均衡；
    - hard：视角更随机，蓝面可能是出现次数较少的面，选项组合更“迷惑”。

### 常用可自定义配置字段

在 YAML/JSON 配置文件的每个任务条目下，可以按需覆盖以下字段，以替代默认预设：

- 通用：
  - `num_questions`：每个任务生成的题目数；
  - `image_resolution`: `[宽, 高]`；
  - `difficulty`: `"easy" | "medium" | "hard"`；
  - `num_distractors`: 干扰选项数量（大部分 3D 任务使用）。

- 组合/旋转/投影类任务（3D 形状组合、旋转、视图匹配）：
  - `num_cells_min`, `num_cells_max`：形状中方块数量范围；
  - `use_rectangular_prisms`: 是否启用长方体；
  - `rectangular_prism_prob`: 使用长方体的概率；
  - `distractor_difficulty`: 干扰形状改动强度（0.0–1.0，越大差异越大）。

- 折叠 & 蓝面任务：
  - `ortho_scale`: 正交相机视场大小（数值越小物体越大），常用于 `3d_shape_finding`；
  - `lucide_icons`: 要使用的 Lucide 图标 slug 列表；
  - `lucide_download`: 是否在运行时联网下载/更新图标（预缓存完通常设为 `false`）。

示例：在 YAML 中微调某个任务的复杂度与干扰强度：

```yaml
tasks:
  - task: 3d_projection
    output_dir: blender_dataset/view_matching
    difficulty: medium
    num_cells_min: 4
    num_cells_max: 9
    distractor_difficulty: 0.35
```

这样可以在保留 `difficulty="medium"` 行为的前提下，将形状略微变复杂，并轻微提高干扰项的差异度。

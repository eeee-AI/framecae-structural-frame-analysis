"""Read and verify the actual 01 solution before deriving local cut motions."""
import hashlib
import json
import numpy as np
from framecae.io.payload import payload_to_model, model_to_payload
from framecae.solver.assembler import assemble_stiffness, assemble_load_vector
from framecae.solver.static_solver import StaticSolver, StaticResult


def canonical_model(model):
    data = model_to_payload(model)
    for key, rows in data.items():
        if isinstance(rows, list):
            data[key] = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))
    return data


def read_solution(request, model):
    supplied = request.get('globalSolution')
    if supplied is None:
        result = StaticSolver(method='ldlt' if len(model.nodes)*6 <= 2000 else 'scipy').solve(model)
        source = '01_solver_recomputed_from_current_model'
    else:
        if not isinstance(supplied, dict) or not isinstance(supplied.get('nodes'), list):
            raise ValueError('01 结果必须包含 solvedModel 和逐节点六自由度位移。')
        if canonical_model(payload_to_model(supplied.get('solvedModel'))) != canonical_model(model):
            raise ValueError('01 结果与当前模型不一致，请重新确认并计算 01。')
        K = assemble_stiffness(model)
        F = assemble_load_vector(model)
        u = np.zeros(model.number_dofs())
        seen = set()
        for row in supplied['nodes']:
            nid = int(row['id'])
            value = np.asarray(row.get('displacement'), dtype=float)
            if nid not in model.nodes or nid in seen or value.shape != (6,) or not np.isfinite(value).all():
                raise ValueError('01 结果含重复、缺失或无效的节点位移。')
            seen.add(nid)
            u[model.nodes[nid].dof_indices] = value
        if seen != set(model.nodes):
            raise ValueError('01 结果没有覆盖当前模型的全部节点。')
        prescribed = model.constrained_dof_values()
        if any(abs(u[k]-v) > 1e-12 for k, v in prescribed.items()):
            raise ValueError('01 位移与当前支座约束不一致。')
        reaction = K@u-F
        result = StaticResult(u, np.asarray(reaction), K, F, 'provided_01')
        source = 'confirmed_01_result'
    free = np.setdiff1d(np.arange(len(result.displacements)), list(model.constrained_dof_values()))
    residual = result.stiffness@result.displacements-result.loads
    # Scale by the actual force terms rather than the usually-zero applied free load.
    scale = max(np.linalg.norm(result.loads), np.linalg.norm(result.stiffness@result.displacements), 1.)
    relative = float(np.linalg.norm(residual[free])/scale)
    if relative > 1e-8:
        raise ValueError(f'01 结果不满足当前整体方程，残差 {relative:.3g}；请重算 01。')
    signature = hashlib.sha256(json.dumps(canonical_model(model), sort_keys=True).encode()).hexdigest()
    return result, {'source': source, 'modelFingerprint': signature, 'relativeResidual': relative,
                    'solutionMethod': result.solution_method, 'nodeCount': len(model.nodes)}

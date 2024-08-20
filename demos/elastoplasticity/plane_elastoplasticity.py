# %% [markdown]
# # Plane elastoplasticity

# %%
import numpy as np
import matplotlib.pyplot as plt
import jax.numpy as jnp
from mpi4py import MPI
import ufl
from dolfinx import io, fem
from dolfinx.cpp.nls.petsc import NewtonSolver
from dolfinx.common import list_timings, TimingType
from dolfinx_materials.quadrature_map import QuadratureMap
from dolfinx_materials.solvers import NonlinearMaterialProblem
from dolfinx_materials.python_materials import (
    ElastoPlasticIsotropicHardening,
    LinearElasticIsotropic,
)
from generate_mesh import generate_perforated_plate
import jax


jax.profiler.start_trace("/tmp/tensorboard")

# %% [markdown]
# We first define our elastoplastic material using the `ElastoPlasticIsotropicHardening` class which represents a von Mises elastoplastic material which takes as input arguments a `LinearElasticIsotropic` material and a custom hardening yield stress function. Here we use a Voce-type exponential harding such that:
#
# $$
# \sigma_Y(p) = \sigma_0 + (\sigma_u-\sigma_0)\exp(-bp)
# $$
# where $\sigma_0$ and $\sigma_u$ are the initial and final yield stresses respectively and $b$ is a hardening parameter controlling the rate of convergence from $\sigma_0$ to $\sigma_u$.

# %%
E = 70e3
sig0 = 350.0
sigu = 500.0
b = 1e3
elastic_model = LinearElasticIsotropic(E=70e3, nu=0.3)


def yield_stress(p):
    return sig0 + (sigu - sig0) * (1 - jnp.exp(-b * p))
    # return sig0 + E/100*p


material = ElastoPlasticIsotropicHardening(elastic_model, yield_stress)

# %% [markdown]
# We then generate the mesh of a rectangular plate of dimensions $L_x\times L_y$ perforated by a circular hole of radius R at its center.

# %%
Lx = 1.0
Ly = 2.0
R = 0.2
mesh_sizes = (0.01, 0.2)
domain, markers, facets = generate_perforated_plate(Lx, Ly, R, mesh_sizes)
ds = ufl.Measure("ds", subdomain_data=facets)

# %%
order = 2
deg_quad = 2 * (order - 1)
shape = (2,)

V = fem.functionspace(domain, ("P", order, shape))
bottom_dofs = fem.locate_dofs_topological(V, 1, facets.find(1))
top_dofs = fem.locate_dofs_topological(V, 1, facets.find(2))

uD_b = fem.Function(V)
uD_t = fem.Function(V)
bcs = [fem.dirichletbc(uD_t, top_dofs), fem.dirichletbc(uD_b, bottom_dofs)]


def strain(u):
    return ufl.as_vector(
        [
            u[0].dx(0),
            u[1].dx(1),
            0.0,
            1 / np.sqrt(2) * (u[1].dx(0) + u[0].dx(1)),
            0.0,
            0.0,
        ]
    )


# %%
du = ufl.TrialFunction(V)
v = ufl.TestFunction(V)
u = fem.Function(V)

# %%
qmap = QuadratureMap(domain, deg_quad, material)
qmap.register_gradient(material.gradient_names[0], strain(u))

# %%
sig = qmap.fluxes["Stress"]
Res = ufl.dot(sig, strain(v)) * qmap.dx
Jac = qmap.derivative(Res, u, du)

# %%
problem = NonlinearMaterialProblem(qmap, Res, Jac, u, bcs)
newton = NewtonSolver(MPI.COMM_WORLD)
newton.rtol = 1e-4
newton.atol = 1e-4
newton.convergence_criterion = "residual"
newton.max_it = 20

# %%
N = 10
Eyy = np.linspace(0, 3e-3, N + 1)
Syy = np.zeros_like(Eyy)
for i, eyy in enumerate(Eyy[1:]):
    uD_t.vector.array[1::2] = eyy * Ly

    converged, it = problem.solve(newton)

    p = qmap.project_on("p", ("DG", 0))
    stress = qmap.project_on("Stress", ("DG", 0))

    Syy[i + 1] = fem.assemble_scalar(fem.form(stress[1] * ds(2))) / Lx

# %%
list_timings(domain.comm, [TimingType.wall, TimingType.user])
jax.profiler.stop_trace()
# %%
plt.figure()
plt.plot(Eyy, Syy, "-o")
plt.xlabel(r"Strain $\varepsilon_{yy}$")
plt.ylabel(r"Stress $\sigma_{yy}$")
plt.savefig(f"{material.name}_stress_strain.pdf")
res = np.zeros((len(Eyy), 2))
res[:, 0] = Eyy
res[:, 1] = Syy
np.savetxt(f"plasticity_results.csv", res, delimiter=",")

# %%

import mgis.behaviour as mgis_bv


path = "/home/hannahk/Dokumente/digitale_Ablage_Promotion/01_Programs/dolfinx_materials/demos/mfront/finite_strain_elastoplasticity/src/libBehaviour.so"
name = "SaintVenantKirchhoffElasticity"
hypothesis = mgis_bv.Hypothesis.PlaneStrain
material_properties={"YoungModulus":2e5,"PoissonRatio": 0.3}        
integration_type = (
            mgis_bv.IntegrationType.IntegrationWithConsistentTangentOperator
        )
dt = 1
is_finite_strain = mgis_bv.isStandardFiniteStrainBehaviour(path, name)
assert is_finite_strain

# finite strain options
bopts = mgis_bv.FiniteStrainBehaviourOptions()
bopts.stress_measure = mgis_bv.FiniteStrainBehaviourOptionsStressMeasure.PK2
bopts.tangent_operator = (
    mgis_bv.FiniteStrainBehaviourOptionsTangentOperator.DS_DEGL
)

b = mgis_bv.load(bopts, path, name, hypothesis)
bd = mgis_bv.BehaviourData(b)
bd.dt = dt
bd.rdt = dt
bd.K[0, 0] = 4 # consistant tangent
#bd.K[0, 1] = 1 # PK2
#bd.K[0, 2] = 1 # dPK2/dEGL
for k, v in material_properties.items():
    mgis_bv.setMaterialProperty(bd.s1, k, v)

bd.s1.gradients[:] = [1, 1, 1, 1, 0]
bdv = mgis_bv.make_view(bd)
result = mgis_bv.integrate(bdv, b)
print(result)
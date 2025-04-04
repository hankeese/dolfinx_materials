#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MFrontNonlinearMaterial class

@author: Jeremy Bleyer, Ecole des Ponts ParisTech,
Laboratoire Navier (ENPC,IFSTTAR,CNRS UMR 8205)
@email: jeremy.bleyer@enpc.fr
"""
import mgis.behaviour as mgis_bv
from dolfinx_materials import PerformanceWarning
import subprocess
import os
import warnings


# we filter out brackets from MFront variable names as it messes up with FFCx
def filter_names(function):
    def new_function(self):
        return [f.replace("[", "").replace("]", "") for f in function(self)]

    return new_function


mgis_hypothesis = {
    "plane_strain": mgis_bv.Hypothesis.PlaneStrain,
    "plane_stress": mgis_bv.Hypothesis.PlaneStress,
    "3d": mgis_bv.Hypothesis.Tridimensional,
    "axisymmetric": mgis_bv.Hypothesis.Axisymmetrical,
}


class MFrontMaterial:
    """
    This class is used to define a material behavior compiled with MFront.
    """

    def __init__(
        self,
        path,
        name,
        hypothesis="3d",
        material_properties={},
        parameters={},
        rotation_matrix=None,
        dt=0,
        stress_measure = mgis_bv.FiniteStrainBehaviourOptionsStressMeasure.PK1,
        tangent_operator = mgis_bv.FiniteStrainBehaviourOptionsTangentOperator.DPK1_DF,
    ):
        """
        Parameters
        -----------

        path : str
            path to the 'libMaterial.so' library containing MFront material laws
        name : str
            name of the MFront behaviour
        hypothesis : {"plane_strain", "3d", "axisymmetric"}
            modelling hypothesis
        material_properties : dict
            a dictionary of material properties. The dictionary keys must match
            the material property names declared in the MFront behaviour. Values
            can be constants or functions.
        parameters : dict
            a dictionary of parameters. The dictionary keys must match the parameter
            names declared in the MFront behaviour. Values must be constants.
        rotation_matrix : Numpy array, list of list, UFL matrix
            a 3D rotation matrix expressing the rotation from the global
            frame to the material frame. The matrix can be spatially variable
            (either UFL matrix or function of Tensor type)
        """
        self.path = str(path)  # ensure string in case we use a PosixPath from pathlib
        self.name = name
        # Defining the modelling hypothesis
        self.hypothesis = mgis_hypothesis[hypothesis]
        self.material_properties = material_properties
        self.rotation_matrix = rotation_matrix
        self.integration_type = (
            mgis_bv.IntegrationType.IntegrationWithConsistentTangentOperator
        )
        self.dt = dt
        # Loading the behaviour
        self.load_behaviour(self.path, stress_measure, tangent_operator)

        self.update_parameters(parameters)

    def load_behaviour(self, path, stress_measure, tangent_operator):
        self.is_finite_strain = mgis_bv.isStandardFiniteStrainBehaviour(path, self.name)
        if self.is_finite_strain:
            # finite strain options
            bopts = mgis_bv.FiniteStrainBehaviourOptions()
            bopts.stress_measure = stress_measure
            bopts.tangent_operator = tangent_operator
            self.behaviour = mgis_bv.load(bopts, path, self.name, self.hypothesis)
        else:
            self.behaviour = mgis_bv.load(path, self.name, self.hypothesis)

    def set_data_manager(self, ngauss):
        # Setting the material data manager
        self.data_manager = mgis_bv.MaterialDataManager(self.behaviour, ngauss)
        self.initialize_external_state_variable("Temperature", 293.15)
        self.update_external_state_variable("Temperature", 293.15)

    def update_parameters(self, parameters):
        for key, value in parameters.items():
            self.behaviour.setParameter(key, value)

    def update_material_property(self, name, values):
        for s in [self.data_manager.s0, self.data_manager.s1]:
            if type(values) in [int, float]:
                mgis_bv.setMaterialProperty(s, name, values)
            else:
                mgis_bv.setMaterialProperty(
                    s,
                    name,
                    values,
                    mgis_bv.MaterialStateManagerStorageMode.LocalStorage,
                )

    def _set_external_state_variable(self, state, name, values):
        if type(values) in [int, float]:
            mgis_bv.setExternalStateVariable(state, name, values)
        else:
            mgis_bv.setExternalStateVariable(
                state,
                name,
                values,
                mgis_bv.MaterialStateManagerStorageMode.LocalStorage,
            )

    def update_external_state_variable(self, name, values):
        self._set_external_state_variable(self.data_manager.s1, name, values)

    def initialize_external_state_variable(self, name, values):
        self._set_external_state_variable(self.data_manager.s0, name, values)

    def get_parameter(self, name):
        return self.behaviour.getParameterDefaultValue(name)

    @property
    def parameter_names(self):
        return self.behaviour.params

    @property
    def material_property_names(self):
        return [svar.name for svar in self.behaviour.mps]

    @property
    @filter_names
    def external_state_variable_names(self):
        return [svar.name for svar in self.behaviour.external_state_variables]

    @property
    @filter_names
    def internal_state_variable_names(self):
        return [svar.name for svar in self.behaviour.internal_state_variables]

    @property
    @filter_names
    def gradient_names(self):
        return [svar.name for svar in self.behaviour.gradients]

    @property
    @filter_names
    def flux_names(self):
        return [svar.name for svar in self.behaviour.thermodynamic_forces]

    @property
    def gradients(self):
        return {k: dim for k, dim in zip(self.gradient_names, self.gradient_sizes)}

    @property
    def fluxes(self):
        return {k: dim for k, dim in zip(self.flux_names, self.flux_sizes)}

    @property
    def internal_state_variables(self):
        return {
            k: dim
            for k, dim in zip(
                self.internal_state_variable_names,
                self.internal_state_variable_sizes,
            )
        }

    @property
    def variables(self):
        dict_grad = self.gradients
        dict_flux = self.fluxes
        dict_isv = self.internal_state_variables
        return {**dict_grad, **dict_flux, **dict_isv}

    @property
    def material_property_sizes(self):
        return [
            mgis_bv.getVariableSize(svar, self.hypothesis)
            for svar in self.behaviour.mps
        ]

    @property
    def external_state_variable_sizes(self):
        return [
            mgis_bv.getVariableSize(svar, self.hypothesis)
            for svar in self.behaviour.external_state_variables
        ]

    @property
    def internal_state_variable_sizes(self):
        return [
            mgis_bv.getVariableSize(svar, self.hypothesis)
            for svar in self.behaviour.internal_state_variables
        ]

    @property
    def has_internal_state_variables(self):
        return len(self.behaviour.internal_state_variables) > 0

    @property
    def gradient_sizes(self):
        return [
            mgis_bv.getVariableSize(svar, self.hypothesis)
            for svar in self.behaviour.gradients
        ]

    @property
    def flux_sizes(self):
        return [
            mgis_bv.getVariableSize(svar, self.hypothesis)
            for svar in self.behaviour.thermodynamic_forces
        ]

    @property
    def tangent_block_names(self):
        return [(t[0].name, t[1].name) for t in self.behaviour.tangent_operator_blocks]

    @property
    def tangent_block_sizes(self):
        return [
            tuple([mgis_bv.getVariableSize(tt, self.hypothesis) for tt in t])
            for t in self.behaviour.tangent_operator_blocks
        ]

    @property
    def tangent_blocks(self):
        return {
            k: dim for k, dim in zip(self.tangent_block_names, self.tangent_block_sizes)
        }

    def integrate(self, eps):
        self.data_manager.s1.gradients[:, :] = eps
        # TODO Clarify settings of K, if at all necessary, depending on the
        # PK1/PK2 etc.
        self.data_manager.allocateArrayOfTangentOperatorBlocks()
        K = self.data_manager.K
        K[:, 0, 0] = 4  # Consistent tangent operator
        K[:, 0, 1] = 1  # 0 - Cauchy, 1 - PK2, 2 - PK1
        K[:, 0, 2] = 1  # 0 - DCauchy/DDefGrad, 1 - DPK2/DS_DEGL, 2 - PK1/DDefGrad
        integrate_status = mgis_bv.integrate(
            self.data_manager, self.integration_type, self.dt, 0, self.data_manager.n
        )
        if integrate_status < 1:
            warnings.warn(
                "Integration of constitutive law has failed.", PerformanceWarning
            )

        if self.has_internal_state_variables:
            isv = self.data_manager.s1.internal_state_variables
        else:
            isv = []
        if len(K.shape) == 3:
            K = K.reshape((K.shape[0], -1))
        return (
            self.data_manager.s1.thermodynamic_forces,
            isv,
            K,
        )

    def set_initial_state_dict(self, state):
        buff = 0
        for i, s in enumerate(self.gradient_names):
            block_shape = self.gradient_sizes[i]
            if (
                s in state
            ):  # test if in state so that we can update only a few state variables
                self.data_manager.s0.gradients[:, buff : buff + block_shape] = state[s]
            buff += block_shape
        buff = 0
        for i, s in enumerate(self.flux_names):
            block_shape = self.flux_sizes[i]
            if s in state:
                self.data_manager.s0.thermodynamic_forces[
                    :, buff : buff + block_shape
                ] = state[s]
            buff += block_shape
        buff = 0
        for i, s in enumerate(self.internal_state_variable_names):
            block_shape = self.internal_state_variable_sizes[i]
            if s in state:
                self.data_manager.s0.internal_state_variables[
                    :, buff : buff + block_shape
                ] = state[s]
            buff += block_shape

    def get_final_state_dict(self):
        state = {}
        buff = 0
        for i, s in enumerate(self.gradient_names):
            block_shape = self.gradient_sizes[i]
            state[s] = self.data_manager.s1.gradients[:, buff : buff + block_shape]
            buff += block_shape
        buff = 0
        for i, s in enumerate(self.flux_names):
            block_shape = self.flux_sizes[i]
            state[s] = self.data_manager.s1.thermodynamic_forces[
                :, buff : buff + block_shape
            ]
            buff += block_shape
        buff = 0
        for i, s in enumerate(self.internal_state_variable_names):
            block_shape = self.internal_state_variable_sizes[i]
            state[s] = self.data_manager.s1.internal_state_variables[
                :, buff : buff + block_shape
            ]
            buff += block_shape
        return state

    def rotate_gradients(self, gradient_vals, rotation_values):
        mgis_bv.rotateGradients(gradient_vals, self.behaviour, rotation_values)

    def rotate_fluxes(self, flux_vals, rotation_values):
        mgis_bv.rotateThermodynamicForces(flux_vals, self.behaviour, rotation_values)

    def rotate_tangent_operator(self, Ct_vals, rotation_values):
        mgis_bv.rotateTangentOperatorBlocks(Ct_vals, self.behaviour, rotation_values)

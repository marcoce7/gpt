#
#    GPT - Grid Python Toolkit
#    Copyright (C) 2024  Christoph Lehner (christoph.lehner@ur.de, https://github.com/lehner/gpt)
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License along
#    with this program; if not, write to the Free Software Foundation, Inc.,
#    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
import gpt as g
import numpy as np
from gpt.core.group import differentiable_functional

default_topological_charge_cache = {}


def topological_charge(
    U, field=False, trace=True, mask=None, cache=default_topological_charge_cache
):
    Nd = len(U)

    assert Nd == 4

    tag = f"{U[0].otype.__name__}_{U[0].grid}_{Nd}"

    if tag not in cache:
        code = []
        _target = 0
        _P = (0,) * Nd
        temporaries = [
            (0, 1, 2),  # Bx
            (1, 2, 0),  # By
            (2, 0, 1),  # Bz
            (3, 3, 0),  # Ex
            (4, 3, 1),  # Ey
            (5, 3, 2),  # Ez
        ]
        for tmp, mu, nu in temporaries:
            _temp1 = 1 + tmp
            code.append((_temp1, -1, 1.0, g.path().f(mu).f(nu).b(mu).b(nu)))
            code.append((_temp1, _temp1, -1.0, g.path().f(mu).b(nu).b(mu).f(nu)))
            code.append((_temp1, _temp1, 1.0, g.path().f(nu).b(mu).b(nu).f(mu)))
            code.append((_temp1, _temp1, -1.0, g.path().b(nu).b(mu).f(nu).f(mu)))
            code.append(
                (
                    _temp1,
                    _temp1,
                    -1.0,
                    [(_temp1, _P, 1)],
                )
            )

        coeff = 8.0 / (32.0 * np.pi**2) * (0.125**2.0)
        coeff *= U[0].grid.gsites

        for i in range(3):
            code.append(
                (
                    _target,
                    -1 if i == 0 else _target,
                    coeff,
                    [(1 + i, _P, 0), (4 + i, _P, 0)],
                )
            )

        cache[tag] = g.parallel_transport_matrix(U, code, 1)

    T = cache[tag](U)

    # return
    if trace:
        T = g(g.trace(T))

    if mask is not None:
        T *= mask

    if not field:
        T = g.sum(T).real / T.grid.gsites

    return T


def v_projected_gradient(U, mu, nu, right_left):
    Nd = len(U)
    assert Nd == 4

    grad = [g.group.cartesian(U[0]) for i in range(Nd)]
    for gr in grad:
        gr[:] = 0

    grad[mu] += g.cshift(g.adj(U[nu]) * right_left * g.cshift(U[nu], mu, 1), nu, -1) * g.adj(
        U[mu]
    )
    grad[mu] -= U[nu] * g.cshift(right_left, nu, 1) * g.adj(g.cshift(U[nu], mu, 1)) * g.adj(U[mu])

    grad[nu] -= U[nu] * g.cshift(
        g.adj(g.cshift(U[mu], nu, 1)) * g.adj(U[nu]) * right_left, mu, -1
    )
    grad[nu] -= g.cshift(g.adj(U[mu]) * U[nu] * g.cshift(right_left, nu, 1), mu, -1) * g.adj(
        U[nu]
    )

    grad[nu] += right_left * g.cshift(U[nu], mu, 1) * g.adj(g.cshift(U[mu], nu, 1)) * g.adj(U[nu])
    grad[nu] += U[nu] * g.cshift(right_left, nu, 1) * g.adj(g.cshift(U[nu], mu, 1)) * g.adj(U[mu])

    grad[mu] @= g.qcd.gauge.project.traceless_hermitian(grad[mu] / 2j)
    grad[nu] @= g.qcd.gauge.project.traceless_hermitian(grad[nu] / 2j)

    return grad


def v(U, mu, nu):
    return g.eval(
        g.cshift(U[nu], mu, 1) * g.adj(g.cshift(U[mu], nu, 1)) * g.adj(U[nu])
        - g.cshift(g.adj(g.cshift(U[nu], mu, 1)) * g.adj(U[mu]) * U[nu], nu, -1)
    )


def F_projected_gradient(U, mu, nu, right_left):
    Nd = len(U)
    assert Nd == 4

    right_left_s = g.cshift(right_left, mu, 1)
    v_val = v(U, mu, nu)
    grad = v_projected_gradient(U, mu, nu, g(right_left * U[mu]))
    grad2 = v_projected_gradient(U, mu, nu, g(U[mu] * right_left_s))
    for rho in range(Nd):
        grad[rho] += grad2[rho]

    grad[mu] -= g.qcd.gauge.project.traceless_hermitian(U[mu] * v_val * right_left / 2j)
    grad[mu] -= g.qcd.gauge.project.traceless_hermitian(U[mu] * right_left_s * v_val / 2j)

    # left * U[mu] * v * right + left * g.cshift(v * U[mu], mu, -1) * right
    return grad


def field_strength_projected_gradient(U, mu, nu, right_left):
    Nd = len(U)
    assert Nd == 4

    fg1 = F_projected_gradient(U, mu, nu, g(right_left))
    fg2 = F_projected_gradient(U, mu, nu, g(g.adj(right_left)))
    grad = []
    for mu in range(Nd):
        grad.append(g(0.125 * (fg1[mu] - g.adj(fg2[mu]))))
    return grad


def topological_charge_gradient(U, mask=None):
    field_strength = g.qcd.gauge.field_strength

    Bx = field_strength(U, 1, 2)
    By = field_strength(U, 2, 0)
    Bz = field_strength(U, 0, 1)

    Ex = field_strength(U, 3, 0)
    Ey = field_strength(U, 3, 1)
    Ez = field_strength(U, 3, 2)

    if mask is None:
        mask = g.complex(U[0].grid)
        mask[:] = 1.0

    delta = g(
        g.expr(field_strength_projected_gradient(U, 1, 2, g(mask * Ex)))
        + g.expr(field_strength_projected_gradient(U, 3, 0, g(mask * Bx)))
        + g.expr(field_strength_projected_gradient(U, 2, 0, g(mask * Ey)))
        + g.expr(field_strength_projected_gradient(U, 3, 1, g(mask * By)))
        + g.expr(field_strength_projected_gradient(U, 0, 1, g(mask * Ez)))
        + g.expr(field_strength_projected_gradient(U, 3, 2, g(mask * Bz)))
    )

    coeff = 8.0 / (32.0 * np.pi**2)

    ret = []
    for d in delta:
        dQ = g(coeff * d)
        dQ.otype = U[0].otype.cartesian()
        ret.append(dQ)

    return ret


class differentiable_topology(differentiable_functional):
    def __init__(self, mask=None):
        self.mask = mask

    def __call__(self, U):
        return topological_charge(U, mask=self.mask)

    def gradient(self, U, dU):
        gradient = topological_charge_gradient(U, mask=self.mask)
        ret = []
        for u in dU:
            ret.append(gradient[U.index(u)])
        return ret


def projected_gradient_F_projected_gradient(U, mu, nu, right_left, outer_right_left):
    Nd = len(U)
    assert Nd == 4

    right_left_s = g.cshift(right_left, mu, 1)
    v_val = v(U, mu, nu)

    one = g.identity(g.group.cartesian(U[0]))
    grad = projected_gradient_v_projected_gradient(U, mu, nu, right_left, one, outer_right_left)
    grad2 = projected_gradient_v_projected_gradient(U, mu, nu, one, right_left_s, outer_right_left)
    for rho in range(Nd):
        grad[rho] += grad2[rho]

    one = g.identity(g.lattice(grad[0]))
    otype = grad[0].otype

    #grad[mu] -= g.qcd.gauge.project.traceless_hermitian(U[mu] * v_val * right_left / 2j)
    # v_val_1
    grad[mu] -= projected_gradient_traceless_hermitian(
        U[mu] * g.cshift(U[nu], mu, 1) * g.adj(g.cshift(U[mu], nu, 1)) * g.adj(U[nu]) * right_left / 2j,
        one,
        outer_right_left[mu],
        otype
    )
        
    grad[mu] -= projected_gradient_traceless_hermitian(
        - U[mu] * g.adj(g.cshift(U[mu] * g.cshift(U[nu], mu, 1), nu, -1)) / 2j,
        g.cshift(g.adj(right_left) * U[nu], nu, -1),
        g.cshift(outer_right_left[mu], nu, -1),
        otype
    )
        
    grad[nu] -= projected_gradient_traceless_hermitian(
        U[nu] * g.cshift(g.cshift(g.adj(U[mu]), nu, 1) * g.adj(U[nu]) * right_left, mu, -1) / 2j,
        g.cshift(U[mu], mu, -1),
        g.cshift(outer_right_left[mu], mu, -1),
        otype
    )
        
    grad[nu] -= projected_gradient_traceless_hermitian(
        - U[nu] * g.cshift(U[mu], nu, 1) * g.cshift(g.adj(U[nu]), mu, 1) * g.adj(U[mu]) / 2j,
        g.adj(right_left),
        outer_right_left[mu],
        otype
    )

    # v_val_2
    grad[mu] += projected_gradient_traceless_hermitian(
        U[mu] * g.cshift(g.adj(g.cshift(U[nu], mu, 1)) * g.adj(U[mu]) * U[nu], nu, -1) * right_left / 2j,
        one,
        outer_right_left[mu],
        otype
    )
        
    grad[mu] += projected_gradient_traceless_hermitian(
        - U[mu] * g.adj(g.cshift(U[mu], nu, 1) * g.adj(g.cshift(U[nu], mu, 1)))/ 2j,
        g.adj(U[nu] * g.cshift(right_left, nu, 1)),
        g.cshift(outer_right_left[mu], nu, 1),
        otype
    )
        
    grad[nu] += projected_gradient_traceless_hermitian(
        - U[nu] * g.cshift(g.cshift(g.adj(U[mu]), nu, 1), mu, -1) / 2j,
        g.adj(g.cshift(g.adj(U[mu]) * U[nu] * g.cshift(right_left, nu, 1), mu, -1)),
        g.cshift(g.cshift(outer_right_left[mu], nu, 1), mu, -1),
        otype
    )

    grad[nu] += projected_gradient_traceless_hermitian(
        U[nu] * g.cshift(right_left, nu, 1) / 2j,
        g.cshift(U[mu], nu, 1) * g.adj(g.cshift(U[nu], mu, 1)) * g.adj(U[mu]),
        g.cshift(outer_right_left[mu], nu, 1),
        otype
    )

    #grad[mu] -= g.qcd.gauge.project.traceless_hermitian(g(U[mu] * right_left_s * v_val) / 2j)
    grad[mu] -= projected_gradient_traceless_hermitian(
        U[mu] * right_left_s * g.cshift(U[nu], mu, 1) * g.adj(g.cshift(U[mu], nu, 1)) * g.adj(U[nu]) / 2j,
        one,
        outer_right_left[mu],
        otype
    )
        
    grad[mu] -= projected_gradient_traceless_hermitian(
        - U[mu] * g.adj(g.cshift(U[mu] * right_left_s * g.cshift(U[nu], mu, 1), nu, -1)) / 2j,
        g.adj(g.cshift(g.adj(U[nu]), nu, -1)),
        g.cshift(outer_right_left[mu], nu, -1),
        otype
    )

    grad[nu] -= projected_gradient_traceless_hermitian(
        U[nu] * g.cshift(g.cshift(g.adj(U[mu]), nu, 1) * g.adj(U[nu]), mu, -1) / 2j,
        g.cshift(U[mu] * right_left_s, mu, -1),
        g.cshift(outer_right_left[mu], mu, -1),
        otype
    )
        
    grad[nu] -= projected_gradient_traceless_hermitian(
        - U[nu] * g.cshift(U[mu], nu, 1) * g.cshift(g.adj(U[nu]), mu, 1) * g.adj(U[mu] * right_left_s) / 2j,
        one,
        outer_right_left[mu],
        otype
    )

    #v_val_2
    grad[mu] += projected_gradient_traceless_hermitian(
        U[mu] * right_left_s * g.cshift(g.adj(g.cshift(U[nu], mu, 1)) * g.adj(U[mu]) * U[nu], nu, -1) / 2j,
        one,
        outer_right_left[mu],
        otype
    )
        
    grad[mu] += projected_gradient_traceless_hermitian(
        - U[mu] * g.adj(g.cshift(U[mu] * right_left_s, nu, 1) * g.adj(g.cshift(U[nu], mu, 1)))/ 2j,
        g.adj(U[nu]),
        g.cshift(outer_right_left[mu], nu, 1),
        otype
    )
        
    grad[nu] += projected_gradient_traceless_hermitian(
        - U[nu] * g.cshift(g.cshift(g.adj(U[mu] * right_left_s), nu, 1), mu, -1) / 2j,
        g.adj(g.cshift(g.adj(U[mu]) * U[nu], mu, -1)),
        g.cshift(g.cshift(outer_right_left[mu], nu, 1), mu, -1),
        otype
    )

    grad[nu] += projected_gradient_traceless_hermitian(
        U[nu] / 2j,
        g.cshift(U[mu] * right_left_s, nu, 1) * g.adj(g.cshift(U[nu], mu, 1)) * g.adj(U[mu]),
        g.cshift(outer_right_left[mu], nu, 1),
        otype
    )

    return grad


def projected_gradient_field_strength_projected_gradient(U, mu, nu, right_left, outer_right_left):
    Nd = len(U)
    assert Nd == 4

    fg1 = projected_gradient_F_projected_gradient(U, mu, nu, g(right_left), outer_right_left)
    fg2 = projected_gradient_F_projected_gradient(U, mu, nu, g(g.adj(right_left)), outer_right_left)
    grad = []
    for mu in range(Nd):
        grad.append(g(0.125 * (fg1[mu] - g.adj(fg2[mu]))))
        
    return grad


def topological_charge_gradient2(U):
    field_strength = g.qcd.gauge.field_strength

    Bx = field_strength(U, 1, 2)

    delta = g(
        + g.expr(field_strength_projected_gradient(U, 3, 0, Bx))
    )

    coeff = 8.0 / (32.0 * np.pi**2)

    ret = []
    for d in delta:
        dQ = g(coeff * d)
        dQ.otype = U[0].otype.cartesian()
        ret.append(dQ)

    return ret


def projected_gradient_topological_charge_gradient(U, outer):
    field_strength = g.qcd.gauge.field_strength

    Bx = field_strength(U, 1, 2)
    By = field_strength(U, 2, 0)
    Bz = field_strength(U, 0, 1)

    Ex = field_strength(U, 3, 0)
    Ey = field_strength(U, 3, 1)
    Ez = field_strength(U, 3, 2)

    delta = g(
        #g.expr(field_strength_projected_gradient(U, 1, 2, g(mask * Ex)))
        + g.expr(projected_gradient_field_strength_projected_gradient(U, 3, 0, Bx, outer))
        #+ g.expr(field_strength_projected_gradient(U, 3, 0, field_strength_projected_gradient_dinput(U, 3, 0, outer)))
        
        #+ g.expr(field_strength_projected_gradient(U, 2, 0, g(mask * Ey)))
        #+ g.expr(field_strength_projected_gradient(U, 3, 1, g(mask * By)))
        #+ g.expr(field_strength_projected_gradient(U, 0, 1, g(mask * Ez)))
        #+ g.expr(field_strength_projected_gradient(U, 3, 2, g(mask * Bz)))
    )

    coeff = 8.0 / (32.0 * np.pi**2)

    ret = []
    for d in delta:
        dQ = g(coeff * d)
        dQ.otype = U[0].otype.cartesian()
        ret.append(dQ)
    assert False
    return ret


def projected_gradient_traceless_hermitian(U_L, U_R, R_L, otype):
    U_L = g(U_L)
    U_R = g(U_R)
    U = g(U_L * U_R)
    R_L = g(R_L)
    Ndim = otype.shape[0]
    A = g(g.qcd.gauge.project.traceless_anti_hermitian(g(U_L * R_L * U_R * 0.5 - 0.5 * g.adj(U_R) * R_L * g.adj(U_L))) * 0.5j)
    A -= 1.0 / Ndim / 2.0 * g.qcd.gauge.project.traceless_anti_hermitian(U - g.adj(U)) * g.trace(R_L + g.adj(R_L)) * 0.25j
    A.otype = otype
    return A

    
def projected_gradient_v_projected_gradient(U, mu, nu, right, left, outer_right_left):
    Nd = len(U)
    assert Nd == 4

    right_left = g(right * U[mu] * left)

    grad = [g.group.cartesian(U[0]) for i in range(Nd)]
    for gr in grad:
        gr[:] = 0

    otype = grad[0].otype

    one = g.identity(g.lattice(grad[0]))

    #grad[mu] += g.cshift(g.adj(U[nu]) * right * left * g.cshift(U[nu], mu, 1), nu, -1) * g.adj(
    #    U[mu]
    #)

    grad[mu] += projected_gradient_traceless_hermitian(
        - U[mu] * g.cshift(g.cshift(g.adj(U[nu]), mu, 1) * g.adj(right_left) * U[nu], nu, -1) / 2j,
        one,
        outer_right_left[mu],
        otype
    )

    grad[mu] += projected_gradient_traceless_hermitian(
        U[mu] * left * g.cshift(U[nu], mu, 1) * g.cshift(g.adj(U[mu]), nu, 1) / 2j,
        g.adj(U[nu]) * right,
        g.cshift(outer_right_left[mu], nu, 1),
        otype
    )

    grad[nu] += projected_gradient_traceless_hermitian(
        - U[nu] / 2j,
        g.cshift(U[mu], nu, 1) * g.cshift(g.adj(U[nu]), mu, 1) * g.adj(right_left),
        g.cshift(outer_right_left[mu], nu, 1),
        otype
    )

    grad[nu] += projected_gradient_traceless_hermitian(
        U[nu] * g.cshift(g.cshift(g.adj(U[mu]), nu, 1), mu, -1) / 2j,
        g.cshift(g.adj(U[nu]) * right_left, mu, -1),
        g.cshift(g.cshift(outer_right_left[mu], nu, 1), mu, -1),
        otype
    )

    # grad[mu] -= U[nu] * g.cshift(right * left, nu, 1) * g.adj(g.cshift(U[nu], mu, 1)) * g.adj(U[mu])

    grad[mu] -= projected_gradient_traceless_hermitian(
        - U[mu] * g.cshift(U[nu], mu, 1) * g.cshift(g.adj(right_left), nu, 1) * g.adj(U[nu]) / 2j,
        one,
        outer_right_left[mu],
        otype
    )

    grad[mu] -= projected_gradient_traceless_hermitian(
        U[mu] * left * g.cshift(g.cshift(g.adj(U[nu]), mu, 1) * g.adj(U[mu]), nu, -1) / 2j,
        g.cshift(U[nu], nu, -1) * right,
        g.cshift(outer_right_left[mu], nu, -1),
        otype
    )

    grad[nu] -= projected_gradient_traceless_hermitian(
        U[nu] * g.cshift(right_left, nu, 1) * g.adj(g.cshift(U[nu], mu, 1)) * g.adj(U[mu]) / 2j,
        one,
        outer_right_left[mu],
        otype
    )

    grad[nu] -= projected_gradient_traceless_hermitian(
        - U[nu] * g.cshift(g.cshift(g.adj(right_left), nu, 1) * g.adj(U[nu]), mu, -1) / 2j,
        g.cshift(U[mu], mu, -1),
        g.cshift(outer_right_left[mu], mu, -1),
        otype
    )

    #grad[nu] -= U[nu] * g.cshift(g.adj(g.cshift(U[mu], nu, 1)) * g.adj(U[nu]) * right * left, mu, -1)
    grad[mu] -= projected_gradient_traceless_hermitian(
        - U[mu] * g.cshift(g.cshift(g.adj(U[nu]), mu, 1), nu, -1) / 2j,
        g.cshift(g.adj(right_left) * U[nu], nu, -1),
        g.cshift(g.cshift(outer_right_left[nu], mu, 1), nu, -1),
        otype
    )

    grad[mu] -= projected_gradient_traceless_hermitian(
        U[mu] * left / 2j,
        g.cshift(U[nu], mu, 1) * g.adj(g.cshift(U[mu], nu, 1)) * g.adj(U[nu]) * right,
        g.cshift(outer_right_left[nu], mu, 1),
        otype
    )
    
    grad[nu] -= projected_gradient_traceless_hermitian(
        U[nu] * g.cshift(g.adj(g.cshift(U[mu], nu, 1)) * g.adj(U[nu]) * right_left, mu, -1) / 2j,
        one,
        outer_right_left[nu],
        otype
    )
    
    grad[nu] -= projected_gradient_traceless_hermitian(
        -U[nu] * g.cshift(U[mu], nu, 1) * g.cshift(g.adj(U[nu]), mu, 1) / 2j,
        g.adj(right_left),
        g.cshift(outer_right_left[nu], mu, 1),
        otype
    )
        
    #grad[nu] -= g.cshift(g.adj(U[mu]) * U[nu] * g.cshift(right_left, nu, 1), mu, -1) * g.adj(U[nu])
    grad[mu] -= projected_gradient_traceless_hermitian(
        - U[mu] / 2j,
        g.cshift(U[nu], mu, 1) * g.cshift(g.adj(right_left), nu, 1) * g.adj(U[nu]),
        g.cshift(outer_right_left[nu], mu, 1),
        otype
    )

    grad[mu] -= projected_gradient_traceless_hermitian(
        U[mu] * left * g.cshift(g.cshift(g.adj(U[nu]), mu, 1), nu, -1) / 2j,
        g.cshift(g.adj(U[mu]) * U[nu], nu, -1) * right,
        g.cshift(g.cshift(outer_right_left[nu], mu, 1), nu, -1),
        otype
    )
    
    grad[nu] -= projected_gradient_traceless_hermitian(
        U[nu] * g.cshift(right_left, nu, 1) * g.cshift(g.adj(U[nu]), mu, 1) / 2j,
        g.adj(U[mu]),
        g.cshift(outer_right_left[nu], mu, 1),
        otype
    )
    
    grad[nu] -= projected_gradient_traceless_hermitian(
        -U[nu] * g.cshift(g.cshift(g.adj(right_left), nu, 1) * g.adj(U[nu]) * U[mu], mu, -1) / 2j,
        one,
        outer_right_left[nu],
        otype
    )
        
    # grad[nu] += right_left * g.cshift(U[nu], mu, 1) * g.adj(g.cshift(U[mu], nu, 1)) * g.adj(U[nu])
    grad[mu] += projected_gradient_traceless_hermitian(
        - U[mu] * g.cshift(g.cshift(g.adj(U[nu]), mu, 1) * g.adj(right_left), nu, -1) / 2j,
        g.cshift(U[nu], nu, -1),
        g.cshift(outer_right_left[nu], nu, -1),
        otype
    )

    grad[mu] += projected_gradient_traceless_hermitian(
        U[mu] * left * g.cshift(U[nu], mu, 1) * g.adj(g.cshift(U[mu], nu, 1)) * g.adj(U[nu]) / 2j,
        right,
        outer_right_left[nu],
        otype
    )

    grad[nu] += projected_gradient_traceless_hermitian(
        U[nu] * g.cshift(g.adj(g.cshift(U[mu], nu, 1)) * g.adj(U[nu]), mu, -1) / 2j,
        g.cshift(right_left, mu, -1),
        g.cshift(outer_right_left[nu], mu, -1),
        otype
    )
    
    grad[nu] += projected_gradient_traceless_hermitian(
        - U[nu] * g.cshift(U[mu], nu, 1) * g.cshift(g.adj(U[nu]), mu, 1) * g.adj(right_left) / 2j,
        one,
        outer_right_left[nu],
        otype
    )
        
    # grad[nu] += U[nu] * g.cshift(right_left, nu, 1) * g.adj(g.cshift(U[nu], mu, 1)) * g.adj(U[mu])
    grad[mu] += projected_gradient_traceless_hermitian(
        - U[mu] * g.cshift(U[nu], mu, 1) * g.cshift(g.adj(right_left), nu, 1) * g.adj(U[nu]) / 2j,
        one,
        outer_right_left[nu],
        otype
    )

    grad[mu] += projected_gradient_traceless_hermitian(
        U[mu] * left * g.cshift(g.adj(g.cshift(U[nu], mu, 1)) * g.adj(U[mu]), nu, -1) / 2j,
        g.cshift(U[nu], nu, -1) * right,
        g.cshift(outer_right_left[nu], nu, -1),
        otype
    )
    
    grad[nu] += projected_gradient_traceless_hermitian(
        U[nu] * g.cshift(right_left, nu, 1) * g.adj(g.cshift(U[nu], mu, 1)) * g.adj(U[mu]) / 2j,
        one,
        outer_right_left[nu],
        otype
    )
    
    grad[nu] += projected_gradient_traceless_hermitian(
        - U[nu] * g.adj(g.cshift(U[nu] * g.cshift(right_left, nu, 1), mu, -1)) / 2j,
        g.cshift(U[mu], mu, -1),
        g.cshift(outer_right_left[nu], mu, -1),
        otype
    )

    return grad


# tr(U) -> tr(Ta U) Ta = 0.5 * (U + U^dag - 1/3 tr(U+U^dag))
# now: 0.5 * tr(L (U + U^dag - 1/3 tr(U + Udag)) R)
# -> project( U R L - R L U^dag ) - 1/3 Ta tr(Ta (U + Udag)) tr(R L) 
#    = project( U R L + R L U^dag ) - 1/3 project(U + Udag) tr(R L) 

class projected_topology_gradient(differentiable_functional):
    def __init__(self, vector):
        self.vector = vector
        self.left = g.mcolor(vector[0].grid) ##g.group.cartesian(g.mcolor(vector[0].grid))
        self.right = g.copy(self.left)
        g.random("test").cnormal([self.left, self.right])

    def __call__(self, U):
        #        return g.inner_product(self.left, g.qcd.gauge.project.traceless_hermitian(U[0])).real
        gradient = v_projected_gradient(U, 0, 1, g(self.right * U[0] * self.left))
        #gradient = F_projected_gradient(U, 0, 1, g(self.right * self.left))
        #gradient = field_strength_projected_gradient(U, 0, 1, g(self.right * self.left))
        #gradient = topological_charge_gradient2(U)
        return sum([g.inner_product(self.vector[mu], gradient[mu]).real for mu in range(len(gradient))])

    def gradient(self, U, dU):
        #gradient = projected_gradient_traceless_hermitian(U[0], g.adj(self.left))
        #ret = [gradient]
        
        gradient = projected_gradient_v_projected_gradient(U, 0, 1, self.right, self.left, g(g.adj(self.vector)))
        #gradient = projected_gradient_F_projected_gradient(U, 0, 1, g(self.right * self.left), g(g.adj(self.vector)))
        #gradient = projected_gradient_field_strength_projected_gradient(U, 0, 1, g(self.right * self.left), g(g.adj(self.vector)))
        #gradient = projected_gradient_topological_charge_gradient(U, g(g.adj(self.vector)))
        ret = []
        for u in dU:
            ret.append(gradient[U.index(u)])
        return ret

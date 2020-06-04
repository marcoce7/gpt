#
#    GPT - Grid Python Toolkit
#    Copyright (C) 2020  Christoph Lehner (christoph.lehner@ur.de, https://github.com/lehner/gpt)
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
import gpt, cgpt, numpy

def coordinates(o, order = "grid"):
    if type(o) == gpt.grid and o.cb.n == 1:
        dim=len(o.ldimensions)
        top=[ o.processor_coor[i]*o.ldimensions[i] for i in range(dim) ]
        bottom=[ top[i] + o.ldimensions[i] for i in range(dim) ]
        checker_dim_mask=[ 0 ] * dim
        return cgpt.coordinates_from_cartesian_view(top,bottom,checker_dim_mask,None,order)
    elif type(o) == tuple and type(o[0]) == gpt.grid and len(o) == 2:
        dim=len(o[0].ldimensions)
        cb=o[1].tag
        checker_dim_mask=o[0].cb.cb_mask
        cbf=[ o[0].fdimensions[i] // o[0].gdimensions[i] for i in range(dim) ]
        top=[ o[0].processor_coor[i]*o[0].ldimensions[i]*cbf[i] for i in range(dim) ]
        bottom=[ top[i] + o[0].ldimensions[i]*cbf[i] for i in range(dim) ]
        return cgpt.coordinates_from_cartesian_view(top,bottom,checker_dim_mask,cb,order)
    elif type(o) == gpt.lattice:
        return coordinates( (o.grid,o.checkerboard()), order = order )
    elif type(o) == gpt.cartesian_view:
        return cgpt.coordinates_from_cartesian_view(o.top,o.bottom,o.checker_dim_mask,o.cb,order)
    else:
        assert(0)

def momentum_phase(l, k):
    # TODO: add sparse field support (x.internal_coordinates(), x.coordinates())
    x=l.mview_coordinates()
    g=l.grid
    cb=l.checkerboard()
    field=gpt.complex(g)
    field.checkerboard(cb)
    if type(k) == numpy.ndarray:
        k=k.tolist()
    field[x]=cgpt.coordinates_momentum_phase(x,k,g.precision)
    l @= field * l
    return l

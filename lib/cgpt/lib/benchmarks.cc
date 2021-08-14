/*
    GPT - Grid Python Toolkit
    Copyright (C) 2020  Christoph Lehner (christoph.lehner@ur.de, https://github.com/lehner/gpt)

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program; if not, write to the Free Software Foundation, Inc.,
    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
*/
#include "lib.h"
#include "benchmarks.h"

/*
template<typename uncompressed_t, typename compressed_t>
class iCompressed {
public:
  typedef typename uncompressed_t::scalar_type scalar_type;
  typedef typename uncompressed_t::scalar_object scalar_object;
  typedef typename uncompressed_t::vector_type vector_type;
  typedef typename uncompressed_t::vector_typeD vector_typeD;
  typedef iCompressed<uncompressed_t,compressed_t> this_t;

  compressed_t data;

  accelerator iCompressed() = default;

  iCompressed(const Zero & zz) {
  }

  friend accelerator_inline scalar_object Reduce(const this_t & a) {
    return scalar_object();
  }
  
  friend accelerator_inline this_t operator+(const this_t & a, const this_t & b) {
    return this_t();
  }

  friend accelerator_inline uncompressed_t coalescedRead(const this_t& c) {
    return uncompressed_t();
  }

  friend accelerator_inline void coalescedWrite(this_t& c, const uncompressed_t & u) {
  }

  friend accelerator_inline auto innerProductD(const this_t& left,
					       const this_t& right)
    -> decltype(innerProductD(uncompressed_t(),uncompressed_t())) {
    return innerProductD(uncompressed_t(),uncompressed_t());
  }

  friend void cgpt_lattice_convert_from(Lattice<this_t>& dst,cgpt_Lattice_base* src) {
  }

  friend int singlet_rank(const this_t& c) {
    return singlet_rank(uncompressed_t());
  }

  friend const std::string get_otype(const Lattice<this_t>& l) {
    return "";
  }

};

template<typename uncompressed_t, typename compressed_t>
class GridTypeMapper<iCompressed<uncompressed_t,compressed_t>> {
public:
  constexpr static int count = GridTypeMapper<uncompressed_t>::count;
};

void mask() {

    int lat = 8;
  Coordinate simd_layout = GridDefaultSimd(Nd,vComplex::Nsimd());
  Coordinate mpi_layout  = GridDefaultMpi();
  Coordinate latt_size  ({lat*mpi_layout[0],lat*mpi_layout[1],lat*mpi_layout[2],lat*mpi_layout[3]});
  GridCartesian     Grid(latt_size,simd_layout,mpi_layout);

  //cgpt_Lattice< iCompressed< iSinglet<vComplexD>, short > > a(&Grid);

  //autoView(a_v,a,CpuWrite);
  //std::cout << GridLogMessage << "Test " << sizeof(a_v[0]) << std::endl;

  //GridParallelRNG          pRNG(&Grid);      pRNG.SeedFixedIntegers(std::vector<int>({45,12,81,9}));
  //random(pRNG,b);
  //a = Zero();
}
*/

//	  auto l_v = l.View(mode);                              \
//	  ViewCloser<decltype(l_v)> _autoView##l_v(l_v);

class ViewContainerBase {
public:
  virtual ~ViewContainerBase() {};
};

template<class View> 
class ViewContainer : public ViewContainerBase {
public:
  View v;
  
  ViewContainer(View &_v) : v(_v) {};
  virtual ~ViewContainer() { v.ViewClose(); }
};

struct micro_kernel_arg_t {
  std::vector<ViewContainerBase*> views;
  size_t o_sites;

  template<class T>
  void add(Lattice<T>& l, ViewMode mode) {
    size_t _o_sites = l.Grid()->oSites();
    if (views.size() == 0) {
      o_sites = _o_sites;
    } else {
      ASSERT(o_sites == _o_sites);
    }
    auto l_v = l.View(mode);
    views.push_back(new ViewContainer<decltype(l_v)>(l_v));
  }

  void release() {
    for (auto x : views)
      delete x;
  }

};

typedef void (* micro_kernel_action_t)(const micro_kernel_arg_t & arg, size_t i0, size_t i1);

struct micro_kernel_t {
  micro_kernel_action_t action;
  micro_kernel_arg_t arg;
};

#define prefetch(a) {                                   \
  vComplexD* tmp = (vComplexD*)&a;                      \
  for (int z=0;z<sizeof(a)/sizeof(vComplexD);z++)       \
    __builtin_prefetch (&tmp[z]);                       \
}

void mk_su3_mul(const micro_kernel_arg_t & arg, size_t i0, size_t i1) {
  typedef typename LatticeColourMatrixD::vector_object vobj;
  typedef typename LatticeColourMatrixD::scalar_object sobj;

  auto a_v = ((ViewContainer<LatticeView<vobj>>*)arg.views[0])->v;
  auto a_p = &a_v[i0];

  auto b_v = ((ViewContainer<LatticeView<vobj>>*)arg.views[1])->v;
  auto b_p = &b_v[i0];

  auto c_v = ((ViewContainer<LatticeView<vobj>>*)arg.views[2])->v;
  auto c_p = &c_v[i0];

  //size_t pf = 0;
#ifndef GRID_HAS_ACCELERATOR
  thread_for_in_region(idx, i1-i0, {
      //prefetch(b_p[idx+pf]);
      //prefetch(c_p[idx+pf]);
    
      a_p[idx] = b_p[idx] * c_p[idx];
    });
#else
  accelerator_forNB(idx, i1-i0, sizeof(vobj)/sizeof(sobj), {
      coalescedWrite(a_p[idx], coalescedRead(b_p[idx]) * coalescedRead(c_p[idx]));
    });
#endif
}

void eval_micro_kernels(const std::vector<micro_kernel_t> & kernels, size_t block_size) {

  size_t n = kernels.size();

  size_t o_sites = kernels[0].arg.o_sites;

#ifndef GRID_HAS_ACCELERATOR
  thread_region
    {
      
      for (size_t j=0;j<(o_sites + block_size - 1)/block_size;j++) {

        for (size_t i=0;i<n;i++) {
          auto& k = kernels[i];
          
          size_t j0 = std::min(j*block_size, o_sites);
          size_t j1 = std::min(j0 + block_size, o_sites);
          k.action(k.arg, j0, j1);
        }

        //#pragma omp barrier
      }      
    }
#else
   for (size_t j=0;j<(o_sites + block_size - 1)/block_size;j++) {

     for (size_t i=0;i<n;i++) {
       auto& k = kernels[i];
       
       size_t j0 = std::min(j*block_size, o_sites);
       size_t j1 = std::min(j0 + block_size, o_sites);
       k.action(k.arg, j0, j1);
     }
     
     //#pragma omp barrier
   }
   accelerator_barrier(dummy);
#endif
}

static void micro_kernels(int lat) {
  Coordinate simd_layout = GridDefaultSimd(Nd,vComplex::Nsimd());
  Coordinate mpi_layout  = GridDefaultMpi();
  Coordinate latt_size  ({lat*mpi_layout[0],lat*mpi_layout[1],lat*mpi_layout[2],lat*mpi_layout[3]});
  GridCartesian     Grid(latt_size,simd_layout,mpi_layout);

  typedef LatticeColourMatrixD Lat;
  Lat a(&Grid), b(&Grid), c(&Grid), d(&Grid);

  size_t block_size = atoi(getenv("BLOCK_SIZE"));
  std::cout << GridLogMessage << "Cache-size: " << block_size * sizeof(Lat::vector_object) << std::endl;
  std::cout << GridLogMessage << "Lattice-size: " << Grid.oSites() * sizeof(Lat::vector_object) << std::endl;
    
  GridParallelRNG          pRNG(&Grid);      pRNG.SeedFixedIntegers(std::vector<int>({45,12,81,9}));
  random(pRNG,a);   random(pRNG,b);

  int N = 10;
  double gb, t0, t1, t2, t3, t4;

 
  gb = 4.0 * 3.0 * sizeof(Lat::scalar_object) * Grid._fsites / 1e9 * N;
  t0 = cgpt_time();
  for (int i=0;i<N;i++) {
    c = a*b;
    d = a*c;
    c = a*b;
    d = a*c;
    //d = a*a*b;
  }
  t1 = cgpt_time();
  std::vector<micro_kernel_t> expression;
  micro_kernel_arg_t views_c_a_b, views_d_a_c;

  views_c_a_b.add(c, AcceleratorWriteDiscard);
  views_c_a_b.add(a, AcceleratorRead);
  views_c_a_b.add(b, AcceleratorRead);

  views_d_a_c.add(d, AcceleratorWriteDiscard);
  views_d_a_c.add(a, AcceleratorRead);
  views_d_a_c.add(c, AcceleratorRead);

  expression.push_back({ mk_su3_mul, views_c_a_b });
  expression.push_back({ mk_su3_mul, views_d_a_c });
  expression.push_back({ mk_su3_mul, views_c_a_b });
  expression.push_back({ mk_su3_mul, views_d_a_c });

  t2 = cgpt_time();
    
  Lat d_copy = d;
  d = Zero();

  t3 = cgpt_time();
  for (int i=0;i<N;i++) {
    eval_micro_kernels(expression, block_size);
  }
  t4 = cgpt_time();

  views_c_a_b.release();
  views_d_a_c.release();

  d -= d_copy;
  double err2 = norm2(d);
  
  std::cout << GridLogMessage << gb << " GB at (GridET) " << gb/(t1-t0) << " or (MK) " << gb/(t4-t3) << " GB/s (view open time = " << (t2-t1) << " versus " << (t4-t3) << " ), err = " << err2 << std::endl;

  
}

EXPORT(benchmarks,{
    //mask();
    //half();
    //benchmarks(8);
    //benchmarks(16);
    //benchmarks(32);
    micro_kernels(4);
    micro_kernels(6);
    micro_kernels(8);
    micro_kernels(10);
    micro_kernels(12);
    micro_kernels(16);
    micro_kernels(24);
    return PyLong_FromLong(0);
  });

EXPORT(tests,{
    test_global_memory_system();
    return PyLong_FromLong(0);
  });

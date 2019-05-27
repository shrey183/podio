

// create dataset


#ifndef SimpleStruct_H
#define SimpleStruct_H
// Usual include declared
#include <array>
#include <iostream>
#include <string>
#include "H5Cpp.h"
using namespace H5;

// Declare member names in the header
const H5std_string MEMBER1( "x" );
const H5std_string MEMBER2( "y" );
const H5std_string MEMBER3( "z" );
const H5std_string MEMBER4( "p" );


// Array dimensions for the coordinate p in the struct
hsize_t array_dim[] = {4};


class SimpleStruct
{
public:
	CompType mtype(sizeof(SimpleStruct));
	mtype.insertMember(MEMBER1, HOFFSET(SimpleStruct, x), PredType::NATIVE_INT);
	mtype.insertMember(MEMBER2, HOFFSET(SimpleStruct, y), PredType::NATIVE_INT);
	mtype.insertMember(MEMBER3, HOFFSET(SimpleStruct, z), PredType::NATIVE_INT);
	mtype.insertMember(MEMBER4, HOFFSET(SimpleStruct, p), H5Tarray_create(H5T_NATIVE_INT, 1, array_dim));

 SimpleStruct() : x(0),y(0),z(0) {} SimpleStruct( const int* v) : x(v[0]),y(v[1]),z(v[2]) {}

};

inline std::ostream& operator<<( std::ostream& o,const SimpleStruct& value )
{
  for(int i=0,N= 4;i<N;++i)
      o << value.p[i] << "|" ;
  o << "  " ;
  o << value.x << " " ;
  o << value.y << " " ;
  o << value.z << " " ;
  return o ;
}
#endif

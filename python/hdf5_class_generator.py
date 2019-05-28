 #!/usr/bin/python2
import os
import string
import pickle
import subprocess
import re
import collections
from podio_config_reader import PodioConfigReader, ClassDefinitionValidator
from podio_templates import declarations, implementations
thisdir = os.path.dirname(os.path.abspath(__file__))





class ClassGenerator(object):

	def __init__(self, yamlfile, install_dir, package_name, verbose=True, dryrun=False):

		print 'ClassGenerator __init__ TRIGGERED\n'
		self.yamlfile = yamlfile
		self.install_dir = install_dir
		self.package_name = package_name
		self.template_dir = os.path.join(thisdir, "../templates")
		self.verbose = verbose
		self.buildin_types = ClassDefinitionValidator.buildin_types
		self.created_classes = []
		self.requested_classes = []
		self.reader = PodioConfigReader(yamlfile)
		self.warnings = []
		self.component_members = {}
		self.dryrun = dryrun


	def configure_clang_format(self, apply):

		'''
		USELESS at the moment! 
		'''

		print 'ClassGenerator configure_clang_format TRIGGERED'


		if not apply:
		    self.clang_format = []
		    return
		try:
		    cformat_exe = subprocess.check_output(['which', 'clang-format']).strip()
		except subprocess.CalledProcessError:
		    print ("ERROR: Cannot find clang-format executable")
		    print ("       Please make sure it is in the PATH.")
		    self.clang_format = []
		    return
		self.clang_format = [cformat_exe, "-i",  "-style=file", "-fallback-style=llvm"]


	def process(self):

		print 'ClassGenerator process TRIGGERED\n'

		self.reader.read()
		self.getSyntax = self.reader.options["getSyntax"]
		self.expose_pod_members = self.reader.options["exposePODMembers"]
		
		# print ('yamlfile components\n {}'.format(self.reader.components))
		
		self.process_components(self.reader.components)		
	
	def write_hdf5_component(self, name, members):
		d = collections.OrderedDict()
		
		header_dir = os.path.join(thisdir, self.install_dir,self.package_name,name)
		
		includes = ['// this is generated by podio_class_generator.py\n#include "{}.h"\n'.format(header_dir,name),\
					 '// header required for HDF5\n#include "H5Cpp.h"\n',\
					"// for shared pointers\n#include <memory>\n", \
					"// for printing messages\n#include <iostream>\n"]
					
		namespace = ['using namespace H5;\n']
		
		# need to declare the strings for setting up the struct
		const_dec = ['const H5std_string FILE_NAME("{}_to_HDF5.h5");\n'.format(name), \
						'const H5std_string DATASET_NAME("{}_data");\n'.format(name)]

		# fill the const_dec with each variable in the struct
		# also get array dimensions if any and insert 
		array_dim = {}
		member_map = {}
		count = 1
		
		
		for varName, dtype in members.items():
			# ignore extra code
			if varName != 'ExtraCode':
				declaration = 'const H5std_string MEMBER{}("{}");\n'.format(count, varName)
				member_map[varName] = count
				const_dec.append(declaration)
				count +=1
				if 'std::array' in dtype:
					# get the dimension of the array
					array_dim[varName] = re.findall(r'\d+', dtype)[0]
				
		#print(array_dim)
		rank_declaration = 'const int RANK = 1;\n'
		const_dec.append(rank_declaration)
		
		
		# Now we write the main function
		generic = "int main(int argc, char** argv)"+\
			"{\n"+ \
			"\tif(argc !=2)\n"+\
			"\t\t{\n"+\
				'\t\t\tstd::cout<<"Wrong Input. Run ./SimpleStruct <int size>\\n";\n'+ \
				'\t\t\texit(1);\n' +\
			'\t\t}\n'+\
		'\tconst long long unsigned int SIZE = atoi(argv[1]);\n'
		
		# create an array with elements of type name
		array_dec = "\tstruct {}* p = (struct {}*)malloc(SIZE * sizeof(struct {}));\n".format(name, name, name)
					
		# declare dimension of arrays if any
		h_dec = ''
		for v, d in array_dim.items():
			h_dec = '\thsize_t %s_array_dim[] = {%s};\n;' % (v, d) 
			 
	
		# create compound type
		comp_dec = '\tCompType mtype(sizeof({}));\n'.format(name)
		# c++ to hdf5 datatype map
		dtype_map = {'int': 'PredType::NATIVE_INT',     \
					'double': 'PredType::NATIVE_DOUBLE',\
					'long': 'PredType::NATIVE_LONG',    \
					'char': 'PredType::NATIVE_CHAR',    \
					'float': 'PredType::NATIVE_FLOAT'}
		# different map for array type
		a_type_map = {'int': 'H5T_NATIVE_INT', \
			'double': 'H5T_NATIVE_DOUBLE',		\
			'long': 'H5T_NATIVE_LONG',			\
			'char': 'H5T_NATIVE_CHAR',			\
			'float': 'H5T_NATIVE_FLOAT'}
		
		for varName, dtype in members.items():
			# ignore extra code
			if varName != 'ExtraCode':
				if varName not in array_dim:
					hdf5_dtype = dtype_map[dtype]
					count = member_map[varName]
					comp_dec += '\tmtype.insertMember(MEMBER{}, HOFFSET({}, {}),{});\n'.format(count, name, varName, hdf5_dtype)
													
				else:
					st_index = dtype.find('<') + 1
					end_index = dtype.find(',') 
					data_type = dtype[st_index:end_index].strip()
					hdf5_dtype = a_type_map[data_type]
					count = member_map[varName]
					comp_dec += '\tmtype.insertMember(MEMBER{}, HOFFSET({}, p),H5Tarray_create({}, 1, {}_array_dim));\n'.format(count,name,hdf5_dtype,varName)
								
		till_now = "".join(includes) + "".join(namespace) + "".join(const_dec) \
					 + generic + array_dec + h_dec + comp_dec 
		
		# create file
		file_dec = "\tstd::shared_ptr<H5File> file(new H5File(FILE_NAME, H5F_ACC_TRUNC));\n"
		# create dataset
		data_dec = "\thsize_t dim[] = {SIZE};\n"
		data_dec += "\tDataSpace space(RANK, dim);\n" 
		data_dec += "\tstd::shared_ptr<DataSet> dataset(new DataSet(file->createDataSet(DATASET_NAME, mtype, space)));\n"
		# write data
		data_dec += '\tdataset->write(p, mtype);\n' + '\treturn 0;\n}'
		
		content = till_now + file_dec + data_dec
		filename = "write_{}.cpp".format(name)	
		#print 'HDF5 WRITE DONE\n'
		#print 'filename {}'.format(filename)
		#print 'contents\n'
		#print content
		self.write_file(filename, content)

	def process_components(self, content):

		print 'ClassGenerator process_components TRIGGERED\n'

		self.requested_classes += content.keys()
		for name, components in content.items():
			self.create_component(name, components["Members"])
			self.write_hdf5_component(name, components['Members'])

	def create_component(self, classname, components):
	  """ Create a component class to be used within the data types
		  Components can only contain simple data types and no user
		  defined ones
	  """

	  print 'ClassGenerator create_component TRIGGERED\n'


	  namespace, rawclassname, namespace_open, namespace_close = self.demangle_classname(classname)
	  
	  '''
	  print('demangle_class returns\n')
	  
	  
	  print('namespace {}\n'.format(namespace))
	  print('rawclassname {}\n'.format(rawclassname))
	  print('namespace_open {}\n'.format(namespace_open))
	  print('namespace_close {}\n'.format(namespace_close))
	  '''
	  
	  includes = []
	  members = ""
	  extracode_declarations = ""
	  ostreamComponents = ""
	  printed = [""]
	  self.component_members[classname] = []
	  keys = sorted( components.keys() )

	  ostreamComponents +=  "inline std::ostream& operator<<( std::ostream& o,const " + classname + "& value ){ \n"

	  for name in keys:
	  	print  " comp: " , classname , " name : " , name
		klass = components[ name ]
		if( name != "ExtraCode"):

		  if not klass.startswith("std::array"):
		    ostreamComponents +=  ( '  o << value.%s << " " ;\n' %  name  )
		  else:
		    arrsize = klass[ klass.rfind(',')+1 : klass.rfind('>') ]
		    ostreamComponents +=    '  for(int i=0,N='+arrsize+';i<N;++i)\n'
		    ostreamComponents +=  ( '      o << value.%s[i] << "|" ;\n' %  name  )
		    ostreamComponents +=    '  o << "  " ;\n'
		  klassname = klass
		  mnamespace = ""
		  if "::" in klass:
		    mnamespace, klassname = klass.split("::")
		  if mnamespace == "":
		      members+= "  %s %s;\n" %(klassname, name)
		      self.component_members[classname].append([klassname, name])
		  else:
		    members += " ::%s::%s %s;\n" %(mnamespace, klassname, name)
		    self.component_members[classname].append(["::%s::%s" % (mnamespace, klassname), name])
		  if self.reader.components.has_key(klass):
		      includes.append('#include "%s.h"\n' %(klassname))
		  if "std::array" in klass:
		      includes.append("#include <array>\n")
		      array_type = klass.split("<")[1].split(",")[0]
		      if array_type not in self.buildin_types:
		        if "::" in array_type:
		              array_type = array_type.split("::")[1]
		        includes.append("#include \"%s.h\"\n" % array_type)
		else:
		  # handle user provided extra code
		  if klass.has_key("declaration"):
		    extracode_declarations = klass["declaration"]
		  if klass.has_key("includes"):
		     includes.append(klass["includes"])

	  ostreamComponents +=  "  return o ;\n"
	  ostreamComponents +=  "}\n"
	  # make includes unique and put it in a string
	  includes = ''.join(list(set(includes)))
	  substitutions = { "ostreamComponents" : ostreamComponents,
		                "includes" : includes,
		                "members"  : members,
		                "extracode_declarations" : extracode_declarations,
		                "name"     : rawclassname,
		                "package_name" : self.package_name,
		                "namespace_open" : namespace_open,
		                "namespace_close" : namespace_close
	  }
	  self.fill_templates("Component",substitutions)
	  self.created_classes.append(classname)

	def demangle_classname(self, classname):

		print 'ClassGenerator demangle_classname TRIGGERED\n'

		namespace_open = ""
		namespace_close = ""
		namespace = ""
		rawclassname = ""
		if "::" in classname:
		    cnameparts = classname.split("::")

		    if len(cnameparts) > 2:
		        raise Exception("'%s' defines a type with nested namespaces. Not supported, yet." % classname)
		        namespace, rawclassname = cnameparts
		        namespace_open = "namespace %s {" % namespace
		        namespace_close = "} // namespace %s" % namespace

		else:
		    rawclassname = classname
		return namespace, rawclassname, namespace_open, namespace_close

	def fill_templates(self, category, substitutions):

	  print 'ClassGenerator fill_templates TRIGGERED\n'
	  # "Data" denotes the real class;
	  # only headers and the FN should not contain Data
	  if category == "Data":
		FN = "Data"
		endings = ("h")
	  elif category == "Obj":
		FN = "Obj"
		endings = ("h","cc")
	  elif category == "Component":
		FN = ""
		endings = ("h")
	  elif category == "Object":
		FN = ""
		endings = ("h","cc")
	  elif category == "ConstObject":
		FN = "Const"
		endings = ("h","cc")
	  elif category == "PrintInfo":
		FN = "PrintInfo"
		endings = ("h")
	  else:
		FN = category
		endings = ("h","cc")
	  for ending in endings:
		templatefile = "%s.%s.template" %(category,ending)
		templatefile = os.path.join(self.template_dir,templatefile)
		template = open(templatefile,"r").read()
		content = string.Template(template).substitute(substitutions).expandtabs(2)
		filename = "%s%s.%s" %(substitutions["name"],FN,ending)
		self.write_file(filename, content)

	def write_file(self, name,content):

	  print 'ClassGenerator write_file TRIGGERED\n'

	  #dispatch headers to header dir, the rest to /src
	  # fullname = os.path.join(self.install_dir,self.package_name,name)
	  if name.endswith("h"):
		fullname = os.path.join(self.install_dir,self.package_name,name)
	  else:
		#print 'HDF5 file here'
		fullname = os.path.join(self.install_dir,"src",name)
	  if not self.dryrun:
		#print 'HDF5 file here dryrun'
		print('fullname = {}'.format(fullname))
		open(fullname, "w").write(content)
		if self.clang_format:
		  subprocess.call(self.clang_format + [fullname])





##########################
if __name__ == "__main__":

    from optparse import OptionParser

    usage = """usage: %prog [options] <description.yaml> <targetdir> <packagename>
    Given a <description.yaml>
    it creates data classes
    and a LinkDef.h file in
    the specified <targetdir>:
      <packagename>/*.h
      src/*.cc"""

    parser = OptionParser(usage)
    parser.add_option("-q", "--quiet",
                    action="store_false", dest="verbose", default=True,
                    help="Don't write a report to screen")
    parser.add_option("-d", "--dryrun",
                    action="store_true", dest="dryrun", default=False,
                    help="Do not actually write datamodel files")
    parser.add_option("-c", "--clangformat", dest="clangformat",
                    action="store_true", default=False,
                    help="Apply clang-format when generating code (with -style=file)")
    (options, args) = parser.parse_args()

    if len(args) != 3:
      parser.error("incorrect number of arguments")



    #--- create output directories if they do not exist
    install_path = args[1]
    project = args[2]
    directory = os.path.join( install_path ,"src" )
    if not os.path.exists( directory ):
      os.makedirs(directory)
    directory = os.path.join( install_path , project )

    print("Something happened", install_path, project)


    if not os.path.exists( directory ):
      os.makedirs(directory)

    gen = ClassGenerator(args[0], args[1], args[2], verbose=options.verbose, dryrun=options.dryrun)
    gen.configure_clang_format(options.clangformat)
    gen.process()
    for warning in gen.warnings:
      print (warning)

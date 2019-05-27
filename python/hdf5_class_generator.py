 #!/usr/bin/python2
import os
import string
import pickle
import subprocess
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

        print 'ClassGenerator configure_clang_format TRIGGERED\n'


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
        self.process_components(self.reader.components)
        #self.process_datatypes(self.reader.datatypes)
        self.create_selection_xml()
        self.print_report()

    def process_components(self, content):

        print 'ClassGenerator process_components TRIGGERED\n'

        self.requested_classes += content.keys()
        for name, components in content.items():
            self.create_component(name, components["Members"])

    def create_component(self, classname, components):
      """ Create a component class to be used within the data types
          Components can only contain simple data types and no user
          defined ones
      """

      print 'ClassGenerator create_component TRIGGERED\n'


      namespace, rawclassname, namespace_open, namespace_close = self.demangle_classname(classname)

      includes = []
      members = ""
      extracode_declarations = ""
      ostreamComponents = ""
      printed = [""]
      self.component_members[classname] = []
      #fg: sort the dictionary, so at least we get a predictable order (alphabetical) of the members
      keys = sorted( components.keys() )

      ostreamComponents +=  "inline std::ostream& operator<<( std::ostream& o,const " + classname + "& value ){ \n"

      for name in keys:
#        print  " comp: " , classname , " name : " , name
        klass = components[ name ]
  #    for name, klass in components.items():
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
        fullname = os.path.join(self.install_dir,"src",name)
      if not self.dryrun:
        open(fullname, "w").write(content)
        if self.clang_format:
          subprocess.call(self.clang_format + [fullname])

    def process_datatype(self, classname, definition, is_data=False):
        print 'ClassGenerator process_datatype TRIGGERED\n'

        datatype_dict = {}
        datatype_dict["description"] = definition["Description"]
        datatype_dict["author"] = definition["Author"]
        datatype_dict["includes"] = []
        datatype_dict["members"] = []
        members = definition["Members"]
        for member in members:
            klass = member["type"]
            name = member["name"]
            description = member["description"]
            datatype_dict["members"].append("  %s %s;  ///<%s"
                                            % (klass, name, description))
            if "std::string" == klass:
                datatype_dict["includes"].append("#include <string>")
                self.warnings.append("%s defines a string member %s, that spoils the PODness"
                                     % (classname, klass))
            elif klass in self.buildin_types:
                pass
            elif klass in self.requested_classes:
                if "::" in klass:
                    namespace, klassname = klass.split("::")
                    datatype_dict["includes"].append('#include "%s.h"'
                                                     % klassname)
                else:
                    datatype_dict["includes"].append('#include "%s.h"'
                                                     % klass)
            elif "std::array" in klass:
                datatype_dict["includes"].append("#include <array>")
                array_type = klass.split("<")[1].split(",")[0]
                if array_type not in self.buildin_types:
                  if "::" in array_type:
                        array_type = array_type.split("::")[1]
                  datatype_dict["includes"].append("#include \"%s.h\"\n" % array_type)
            elif "vector" in klass:
                datatype_dict["includes"].append("#include <vector>")
                if is_data:  # avoid having warnings twice
                    self.warnings.append("%s defines a vector member %s, that spoils the PODness" % (classname, klass))
            elif "[" in klass and is_data:  # FIXME: is this only true ofr PODs?
                raise Exception("'%s' defines an array type. Array types are not supported yet." % (classname, klass))
            else:
                raise Exception("'%s' defines a member of a type '%s' that is not (yet) declared!" % (classname, klass))
        # get rid of duplicates:
        datatype_dict["includes"] = list(set(datatype_dict["includes"]))
        return datatype_dict

    def create_selection_xml(self):

        print 'ClassGenerator create_selection_xml TRIGGERED\n'

        content = ""
        for klass in self.created_classes:
            # if not klass.endswith("Collection") or klass.endswith("Data"):
            content += '          <class name="std::vector<%s>" />\n' % klass
            content += """
            <class name="%s">
              <field name="m_registry" transient="true"/>
              <field name="m_container" transient="true"/>
            </class>\n""" % klass

        templatefile = os.path.join(self.template_dir,
                                    "selection.xml.template")
        template = open(templatefile, "r").read()
        content = string.Template(template).substitute({"classes": content})
        self.write_file("selection.xml", content)

    def print_report(self):

        print 'ClassGenerator print_report TRIGGERED\n'
        if self.verbose:
            pkl = open(os.path.join(thisdir, "figure.txt"))
            figure = pickle.load(pkl)
            text = "%s %d %s" % (self.yamlfile,
                             len(self.created_classes),
                             self.install_dir)
            cntr = 0
            print
            for figline, summaryline in zip(figure, text.splitlines()):
                cntr += 1
                print (figline + summaryline)
            for i in xrange(cntr, len(figure)):
                print (figure[i])
            print ("     'Homage to the Square' - Josef Albers")
            print




type_map = {'int':'PredType::NATIVE_INT', ''}

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

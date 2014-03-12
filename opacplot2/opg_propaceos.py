#!/usr/bin/python
# -*- coding: utf-8 -*-
import numpy as np
import re
from scipy.constants import N_A

class OpgPropaceosGrid(object):

    @staticmethod
    def format_array(X, indent=0):
        """ Convert a 1D array containing temperature or density grid to
        ascii format used as input by propaceos."""
        out = []

        X_str = np.array2string(X, max_line_width=140,
                   formatter={'float': lambda x: "% 8.5e" % x},
                   separator='  ')
        X_str = re.sub(r'[\[\]]',' ',X_str) # remove the [ and  ]
        X_str = X_str.split('\n')
        # default indent is 2
        if indent in [0, 1]:
            X_str = [re.sub(r'^' + ' '*(2-indent), '', el) for el in X_str] # remove indents
        elif indent == 2:
            pass
        elif indent>2:
            X_str = [re.sub(r'^', r' '*(indent-2), el) for el in X_str] # indent everything with spaces
        else:
            raise ValueError
        out += X_str
        return '\n'.join(out)

    @staticmethod
    def format_head_grid2(X, var='temp', section='opacity'):
        """Return header line as in [Grid Values] section"""
        out = []
        var_dict  = {'temp': 'Temperature', 'dens': 'Density'}
        section_dict = {'opacity': 'Opacity', 'eos': 'EOS'}
        out += [' {0} grid - {1}:    # array elements = {2}    [format=1]'.format(
            var_dict[var], section_dict[section], len(X))]

        return '\n'.join(out)

    @staticmethod
    def format_grid2(dens, temp):
        """ Given densiity and temperature arrays convert them to a ascii
        propaceos readable [Grid Values] section

        Parameters:
        -----------
          - dens [1D ndarray]: density cm⁻³
          - temp [1D ndarray]: temperature eV
        """

        out = ["[Grid Values]:\n   Format ID = 1\n#"]
        for section in ['opacity', 'eos']:
            for var in ['temp', 'dens']:
                out += [OpgPropaceosGrid.format_head_grid2(locals()[var], var, section)]
                out += [OpgPropaceosGrid.format_array(locals()[var], indent=3)]

        out += ["[End Grid Values]"]

        return '\n'.join(out)

    @staticmethod
    def format_head_grid1(X, var='temp'):
        """ Return header line as in [Propaceos Grid Parameters] section"""
        out = []
        var_dict1  = {'temp': 'Plasma Temperature', 'dens': 'Density', 'nu': "Photon Energy"}
        var_dict2  = {'temp': 'Plasma Temperatures', 'dens': 'Densities', 'nu': "Photon Energy Boundaries"}
        out += [' [table format=1]:    {0} Grid:'.format(var_dict1[var])]
        out += ['  # table rows = {0}'.format(len(X))]
        out += ['  # table cols = 1']
        out += [var_dict2[var]+':']

        return '\n'.join(out)


    @staticmethod
    def format_grid1(dens, temp, nu):
        """ Given densiity and temperature arrays convert them to a ascii
        propaceos readable by [Propaceos Grid Parameters] section

        Parameters:
        -----------
          - dens [1D ndarray]: density cm⁻³
          - temp [1D ndarray]: temperature eV
        """
        out = []

        for var in ['temp', 'dens', 'nu']:
                out += [OpgPropaceosGrid.format_head_grid1(locals()[var], var)]
                out += [OpgPropaceosGrid.format_array(locals()[var], indent=1)]

        out += ["#\n [End Propaceos Grid Parameters] "]

        return '\n'.join(out)


class OpgPropaceosAscii(dict):
    def __init__(self, filename):
        """
        Parse PROPACEOS ascii file

        Parameters:
        -----------
          - filename: filename of the .prp file

        Returns:
        --------
          a dict containing 
        """
        HEADER_LEN = 100
        f_raw = []
        f_star = []
        with open(filename, 'r') as f:
            for line in f:

                f_star.append(re.match(r'\*+\s+.*', line) is not None)
                f_raw.append(line.replace('\n', ''))
                
        f_star = np.array(f_star, dtype=np.int)
        # get section start index 
        section_begin = np.nonzero((np.diff(f_star)==1))[0] + 1
        section_end = np.zeros(len(section_begin), dtype='int32')
        section_end[:-1] = section_begin[1:]
        section_end[-1] = len(f_raw)
        section_mid = np.nonzero((np.diff(f_star)==-1))[0][1:] + 1

        section_idx = np.concatenate(
                           (section_begin[:,np.newaxis],
                            section_mid[:,np.newaxis],
                            section_end[:,np.newaxis]), axis=1)
        

        if not (len(section_mid) == len(section_end) == len(section_begin)):
            raise ValueError

        self._parse_global_header(f_raw[15:section_begin[0]])

        actions = [
            ('mesh parameters for EoS', lambda x, k: self._parse_grid(x, section='eos'), None),
            ('parameters for opacity', lambda x, k: self._parse_grid(x, section='opac'), None),
            ('group structure', lambda x, k: self._parse_groups(x), None),
            ('Ionization Fractions', lambda x, k: self._parse_array(x, k), 'ion_frac'),
            ('Zbar', lambda x, k: self._parse_array(x, k), 'zbar'),
            ('Int. Rosseland Mean Opacity', lambda x, k: self._parse_array(x, k), 'opr_int'),
            ('Int. emis. Planck Mean Opacity', lambda x, k: self._parse_array(x, k), 'emp_int'),
            ('Int. abs. Planck Mean Opacity', lambda x, k: self._parse_array(x, k), 'opp_int'),
            ('Eint', lambda x, k: self._parse_array(x, k), 'eint'),
            ('Eion', lambda x, k: self._parse_array(x, k), 'eion'),
            ('Eele', lambda x, k: self._parse_array(x, k), 'eele'),
            ('Pion', lambda x, k: self._parse_array(x, k), 'pion'),
            ('Pele', lambda x, k: self._parse_array(x, k), 'pele'),
            ('Rosseland Mean Opacity', lambda x, k: self._parse_array(x, k), 'opr_mg'),
            ('emission Planck Mean Opacity', lambda x, k: self._parse_array(x, k), 'emp_mg'),
            ('absorption Planck Mean Opacity', lambda x, k: self._parse_array(x, k), 'opp_mg'),
                  ]

        for key in ['opr_mg', 'emp_mg', 'opp_mg']:
            self[key] = [] 

        for sidx in range(len(section_begin)):
            header_txt = f_raw[section_begin[sidx]:section_mid[sidx]]
            data_txt = f_raw[section_mid[sidx]:section_end[sidx]]
            header = self._parse_header(header_txt)
            for expr, process, var in actions:
                if expr in header:
                    process(data_txt, var)
                    break
        for key in ['opr_mg', 'emp_mg', 'opp_mg']:
            self[key] = np.array(self[key])

        N_temp_eos = self['N_temp_eos']
        N_nion_eos = self['N_nion_eos']
        N_temp_opac = self['N_temp_opac']
        N_nion_opac = self['N_nion_opac']
        self['N_groups'] = N_groups =  len(self['groups']) - 1
        Num_ions = self['Num_ions']

        required_shape = {'zbar':   (N_nion_eos,  N_temp_eos),
                         'eint':    (N_nion_eos,  N_temp_eos),
                         'eele':    (N_nion_eos,  N_temp_eos),
                         'eion':    (N_nion_eos,  N_temp_eos),
                         'pion':    (N_nion_eos,  N_temp_eos),
                         'pele':    (N_nion_eos,  N_temp_eos),
                         'opp_int': (N_nion_opac, N_temp_opac),
                         'opr_int': (N_nion_opac, N_temp_opac),
                         'emp_int': (N_nion_opac, N_temp_opac),
                         "ion_frac": (N_nion_eos,  N_temp_eos, Num_ions),
                         'emp_mg':  (N_nion_opac, N_temp_opac, N_groups),
                         'opp_mg':  (N_nion_opac, N_temp_opac, N_groups),
                         'opr_mg':  (N_nion_opac, N_temp_opac, N_groups),
                        }

        # convert arrays to a correct shape
        for key, new_shape in required_shape.iteritems():
            self[key] = self[key].reshape(new_shape)

        self.remove_extra_qeos_pt()

        self['Abar'] = 1./(np.sum(self['Xnum']/self['Anum']))
        self['rho'] = self['nion']*self['Abar']/N_A

        self['eps_mg'] = self['emp_mg'] / self['opp_mg']
       


    def _parse_global_header(self, f):
        """ Extract a few relevant parameters from the global header """

        str2arr = lambda x: np.fromstring(x, sep=' ')

        expr_list = [
                    ('Num_ions', " number of ions:\s+", lambda x: int(x)),
                    ('Znum', " atomic #s of gases:\s+", str2arr),
                    ('Anum', " atomic weight of gas:\s+", str2arr), 
                    ('Xnum', " relative fractions:\s+", str2arr),
                 ]

        for line in f:
            for key, expr, func in expr_list:
                res = re.match(expr, line)
                if res:
                    self[key] = func(re.sub(expr, '', line))




    @staticmethod
    def _parse_header(f):
        """ Parse header section for every variable """
        txt = ''.join(f)
        txt = re.sub('\*+','', txt)
        txt = re.sub('\s+',' ', txt)
        return txt

    def _parse_grid(self, txt, section='eos'):
        """
        Parse electron densities and temperature grids at the begining
        of the file
        """

        txt = [el for el in txt if el]
        temp_lbl = 'temp_{0}'.format(section)
        nion_lbl = 'nion_{0}'.format(section)
        N_temp_lbl = 'N_'+temp_lbl
        N_nion_lbl = 'N_'+nion_lbl

        # compute how many lines the grid takes
        N_skip = lambda N: int(np.ceil(N/10.))

        # parsing temperature
        self[N_temp_lbl] = int(txt[0])
        N_temp_skip = N_skip( self[N_temp_lbl])
        self[temp_lbl] = self.str2float(txt[1:N_temp_skip+1])

        # parsing density
        self[N_nion_lbl] = int(txt[N_temp_skip+1])
        N_nion_skip = N_skip( self[N_nion_lbl])
        self[nion_lbl] = self.str2float(txt[N_temp_skip+2:N_temp_skip+2+N_nion_skip])

    def _parse_groups(self, txt):
        """Parse radiation groups grid """
        self['groups'] = self.str2float(txt)

    def _parse_array(self, txt, key):
        """
        Save a list of strings as a numpy array.
        """
        if key in ['opp_mg', 'opr_mg', 'emp_mg']:
            self[key].append(self.str2float(txt))
        else:
            self[key] = self.str2float(txt)

    @staticmethod
    def str2float(txt):
        """ Convert a list of strings to numpy array """
        return np.fromstring(' '.join(txt), sep=' ')

    def remove_extra_qeos_pt(self):
        """ Remove extra point on the EoS grid added by QEOS"""
        mask = np.in1d(self['nion_eos'], self['nion_opac'])
        self['nion'] = self['nion_opac']
        self['temp'] = self['temp_opac']
        for key in ['nion_opac', 'nion_eos', 'temp_opac', 'temp_eos']:
            del self[key]

        for key in ['eele', 'eion', 'eint', 'pele', 'pion', 'zbar', 'ion_frac']:
            self[key] = self[key][mask] # remove the few extra points

    def write2hdf(self, filename):
        """ Write data to a hdf5 file """
        import tables
        f = tables.openFile(filename, 'w')
        # writing arrays
        for key in ['nion', 'temp', 'rho',
                    'zbar', 'eint', 'eele', 'eion', 'pion', 'pele',
                    'opp_mg','opr_mg', 'emp_mg',
                    'opp_int','opr_int', 'emp_int',
                    'Znum', 'Anum', 'Xnum'
                   ]:
            atom = tables.Atom.from_dtype(x.dtype)
            ds = f.createCArray(f.root, key, atom, self[key].shape)
            ds[:] = self[key]
        # writing attributes
        #for attr in ['']
        f.close()


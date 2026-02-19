import sys
import os
import numpy as np

# Añadir el directorio raíz al path para poder importar hbit
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src')))

try:
    from hbit.core.sync import find_sync_positions, BARKER_13, BARKER_13_COMPLEMENT
    print("SUCCESS: Constants imported correctly.")
except ImportError as e:
    print(f"ERROR: Could not import constants: {e}")
    sys.exit(1)
except NameError as e:
    print(f"ERROR: Constant not defined: {e}")
    sys.exit(1)

def test_barker_complement():
    print("Testing BARKER_13_COMPLEMENT...")
    
    # Verificar que es el complemento (negativo)
    if np.array_equal(BARKER_13_COMPLEMENT, -BARKER_13):
        print("SUCCESS: BARKER_13_COMPLEMENT is correctly defined as -BARKER_13")
    else:
        print("FAILURE: BARKER_13_COMPLEMENT definition is incorrect")
        sys.exit(1)

    # Crear una señal que contenga el complemento
    # BARKER_13 es: [ 1,  1,  1,  1,  1, -1, -1,  1,  1, -1,  1, -1,  1]
    # COMPLEMENT es: [-1, -1, -1, -1, -1,  1,  1, -1, -1,  1, -1,  1, -1]
    
    # 0s y 1s para la función find_sync_positions
    # Mapeo: -1 -> 0, 1 -> 1. Pero espera, BARKER es la secuencia de correlación (-1/1). 
    # La entrada a find_sync_positions es bits 0/1, que luego se convierten a -1/1.
    # Si BARKER_13_COMPLEMENT espera encontrar el patrón invertido...
    
    # Vamos a probar llamando a la función
    # HEADER (search_header=True) busca BARKER_13
    # FOOTER (search_header=False) busca BARKER_13_COMPLEMENT
    
    # Creemos un bitstream que coincida con el complemento
    # Si BARKER_13_COMPLEMENT es la secuencia objetivo, queremos generar bits que coincidan con ella.
    # Si el valor es 1 en el patrón, bit = 1. Si es -1, bit = 0.
    
    target_pattern = BARKER_13_COMPLEMENT
    bits = [1 if x > 0 else 0 for x in target_pattern]
    bit_stream = "".join(str(b) for b in bits)
    
    print(f"Testing with bitstream matching complement: {bit_stream}")
    
    try:
        positions = find_sync_positions(bit_stream, threshold=0.9, search_header=False)
        print(f"Positions found: {positions}")
        
        if 0 in positions:
            print("SUCCESS: Function find_sync_positions(..., search_header=False) working correctly.")
        else:
            print("FAILURE: Did not find the pattern at index 0.")
            sys.exit(1)
            
    except NameError as e:
         print(f"ERROR during execution: {e}")
         sys.exit(1)
    except Exception as e:
        print(f"ERROR unexpected: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_barker_complement()

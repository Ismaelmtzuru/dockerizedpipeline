import os
import sys
from dotenv import load_dotenv 
import requests
import pyarrow.parquet as pq 
from sqlalchemy import create_engine
import pandas as pd 
import io
import psycopg2

def main():
  
    load_dotenv() 

    try:
        # --- Carga de Variables ---
        user = os.getenv('PG_USER')
        password = os.getenv('PG_PASSWORD')
        host = 'postgres-container' 
        port = os.getenv("PG_PORT")
        db = os.getenv('PG_DB')
        table_name = os.getenv('PG_TABLE_NAME')
        parquet_url = os.getenv('PG_URL')
        parquet_name = 'output.parquet' 

        # --- 2. Descarga y Verificación del Archivo ---
        print(f"1. Descargando archivo desde: {parquet_url}")
        
        try:
            response = requests.get(parquet_url)
            response.raise_for_status() 
            
            with open (parquet_name,'wb') as f:
                f.write(response.content)
            print(f"   Descarga exitosa. Archivo guardado como {parquet_name}")
        except requests.RequestException as e:
            print(f'❌ Error al descargar el archivo: {e}')
            sys.exit(1)

        # --- 3. Conexión y Setup ---
        DB_URL = f'postgresql://{user}:{password}@{host}:{port}/{db}'
        
        # Conexión SQLAlchemy para crear el motor 
        engine = create_engine(DB_URL)
        
        # Prueba de conexión exitosa
        engine.connect().close()
        print(f"2. Conexión exitosa a {host}:{port}/{db}")

        # --- 4. Ingesta RÁPIDA por Lotes (COPY FROM) ---
        parquet_file = pq.ParquetFile(parquet_name)

        # Conexión nativa de psycopg2 para el bucle (más rápida)
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        print("3. Iniciando ingesta rápida por lotes (COPY FROM)...")


        # Bucle para procesar e insertar lotes
        for batch_num, batch in enumerate(parquet_file.iter_batches(batch_size=100000)):
            df = batch.to_pandas()
            
            # Conversión de tipos de datos antes de la ingesta
            df['tpep_pickup_datetime'] = pd.to_datetime(df['tpep_pickup_datetime'])
            df['tpep_dropoff_datetime'] = pd.to_datetime(df['tpep_dropoff_datetime'])
            
            # Crear tabla solo en el primer lote (Garantiza que el schema exista)
            if batch_num == 0:
                print(f"   Creando/Reemplazando tabla '{table_name}'...")
                # Usamos el engine de SQLAlchemy para crear la estructura fácilmente
                df.head(n=0).to_sql(name=table_name, con=engine, if_exists='replace')

            # --- INSERCIÓN RÁPIDA ---
            output = io.StringIO()
            # Escribir el DataFrame al buffer de memoria como un CSV separado por tabuladores
            # header=False para evitar escribir nombres de columna en los datos
            df.to_csv(output, sep='\t', header=False, index=False) 
            output.seek(0) 

            column_list = df.columns.tolist()

            # Ejecutar el comando COPY FROM con la conexión nativa
            cur.copy_from(
                output, 
                table_name, 
                sep='\t', 
                null="",
                columns=column_list
            )
            conn.commit()
            
            print(f'   ✅ Inserted batch {batch_num + 1} ({len(df)} rows)')
        
        print('\nFinished ingesting data into PostgreSQL database')

    # --- Manejo de errores general ---
    except Exception as e:
        # Intenta hacer rollback si una conexión existe
        if 'conn' in locals():
            conn.rollback()
        print(f'❌ Ocurrió un error crítico: {e}')
        sys.exit(1)
    finally:
        # Asegura que la conexión nativa se cierre al finalizar
        if 'conn' in locals():
            cur.close()
            conn.close()

if __name__ == '__main__':
    main()
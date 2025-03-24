from flask import Flask, request, jsonify
import FreeCAD
import Part
import Mesh
import os
from pymongo import MongoClient
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# MongoDB configuration
MONGO_URI = os.getenv("MONGO_URI")  # Get MongoDB URI from .env
DATABASE_NAME = os.getenv("MONGO_DB")  # Get database name from .env
COLLECTION_NAME = os.getenv("file_conversion_next")  # Get collection name from .env

# Initialize MongoDB client
client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]
collection = db[COLLECTION_NAME]

# S3 Configuration (get from .env)
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")  # Get AWS access key from .env
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")  # Get AWS secret key from .env
AWS_REGION = os.getenv("AWS_REGION")  # Get AWS region from .env

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)

def generate_output_file(input_file, output_format):
    """
    Generate the output file name based on the input file name and output format.
    
    :param input_file: Path to the input file
    :param output_format: Desired output format (e.g., "stl", "step")
    :return: Generated output file name
    """
    # Get the base name of the input file (without extension)
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    
    # Append the output format as the new extension
    output_file = f"{base_name}.{output_format.lower()}"
    
    return output_file

def generate_presigned_url(bucket_name, object_name, expiration=3600):
    """
    Generate a pre-signed URL to share an S3 object.

    :param bucket_name: Name of the S3 bucket
    :param object_name: Name of the S3 object (file)
    :param expiration: Time in seconds for the pre-signed URL to remain valid (default: 1 hour)
    :return: Pre-signed URL as a string. If error, returns None.
    """
    try:
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': object_name},
            ExpiresIn=expiration
        )
        return response
    except Exception as e:
        print(f"Error generating pre-signed URL: {e}")
        return None
    
def convert_step(input_file, output_file, output_format, tolerance=0.1):
    """
    Converts a CAD file from one format to another.
    Supported formats: STEP, IGES, STL, OBJ, PLY, BREP, OFF.
    """
    try:
        print("Starting conversion...")
        print(f"Input file: {input_file}")
        print(f"Output file: {output_file}")
        print(f"Output format: {output_format}")

        # Verify input file exists
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")

        # Initialize FreeCAD (if not already initialized)
        print("Initializing FreeCAD...")
        if not FreeCAD.ActiveDocument:
            FreeCAD.newDocument("ConversionDocument")
        print("FreeCAD initialized.")

        # Check the input file extension
        input_extension = os.path.splitext(input_file)[1].lower()

        # Handle OBJ, STL, PLY, and OFF files separately
        if input_extension in (".obj", ".stl", ".ply", ".off"):
            print(f"Loading {input_extension} file as a mesh...")
            mesh = Mesh.Mesh()
            mesh.read(input_file)
            print(f"{input_extension} file loaded. Converting mesh to shape...")
            shape = Part.Shape()
            shape.makeShapeFromMesh(mesh.Topology, tolerance)
            print("Mesh converted to shape.")
        else:
            # Load the input file (for non-mesh formats)
            print(f"Loading input file ({input_extension})...")
            shape = Part.Shape()
            shape.read(input_file)
            print("Input file loaded.")

        # Perform the conversion based on the output format
        print(f"Exporting to {output_format}...")
        if output_format.lower() in ("stp", "step"):
            shape.exportStep(output_file)
        elif output_format.lower() in ("iges", "igs"):
            shape.exportIges(output_file)
        elif output_format.lower() == "stl":
            mesh = Mesh.Mesh(shape.tessellate(tolerance))
            mesh.write(output_file)
        elif output_format.lower() == "obj":
            mesh = Mesh.Mesh(shape.tessellate(tolerance))
            mesh.write(output_file)
        elif output_format.lower() == "ply":
            mesh = Mesh.Mesh(shape.tessellate(tolerance))
            mesh.write(output_file)
        elif output_format.lower() in ("brep", "brp"):
            shape.exportBrep(output_file)
        elif output_format.lower() == "off":
            mesh = Mesh.Mesh(shape.tessellate(tolerance))
            export_off(mesh, output_file)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")

        print(f"File converted successfully: {output_file}")
        return True

    except Exception as e:
        print(f"Error during conversion: {e}")
        return False
    finally:
        # Close the document to free up memory
        if FreeCAD.ActiveDocument:
            FreeCAD.closeDocument(FreeCAD.ActiveDocument.Name)

def export_off(mesh, output_file):
    """
    Exports a FreeCAD mesh to the .off file format.
    """
    try:
        with open(output_file, "w") as f:
            # Write the OFF header
            f.write("OFF\n")
            f.write(f"{len(mesh.Points)} {len(mesh.Facets)} 0\n")

            # Write vertices
            for point in mesh.Points:
                f.write(f"{point.x} {point.y} {point.z}\n")

            # Write faces
            for facet in mesh.Facets:
                vertices = facet.Points
                f.write(f"{len(vertices)} {' '.join(map(str, vertices))}\n")

        print(f"Exported .off file: {output_file}")

    except Exception as e:
        print(f"Error exporting .off file: {e}")

def upload_to_s3(file_name, bucket_name, object_name=None):
    """
    Upload a file to an S3 bucket.

    :param file_name: File to upload
    :param bucket_name: Bucket to upload to
    :param object_name: S3 object name. If not specified, file_name is used
    :return: True if file was uploaded, else False
    """
    if object_name is None:
        object_name = file_name

    try:
        s3_client.upload_file(file_name, bucket_name, object_name)
        print(f"File {file_name} uploaded to {bucket_name}/{object_name}")
        return True
    except FileNotFoundError:
        print(f"The file {file_name} was not found")
        return False
    except NoCredentialsError:
        print("Credentials not available")
        return False
    except PartialCredentialsError:
        print("Incomplete credentials provided")
        return False
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return False


@app.route('/convert', methods=['POST'])
def convert():
    """
    API endpoint to convert CAD files.
    """
    try:
        # Get data from the request
        data = request.json
        input_file = data.get('input_file')  # Path to the input file
        output_format = data.get('output_format')  # Desired output format
        organization_id = data.get('organization_id')  # Required field
        s3_bucket = data.get('s3_bucket')  # Optional field

        if not input_file or not output_format or not organization_id:
            return jsonify({"error": "Missing required parameters: input_file, output_format, organization_id"}), 400

        # Generate the output file name
        output_file = generate_output_file(input_file, output_format)

        # Log conversion details in MongoDB
        conversion_record = {
            "s3_bucket": s3_bucket,
            "status": "PENDING",  # Initial status
            "organization_id": organization_id,
            "expiryAt": datetime.now() + timedelta(days=1),  # Set expiry to 1 day from now
            "error": None
        }
        result = collection.insert_one(conversion_record)
        conversion_id = str(result.inserted_id)

        # Update status to PROCESSING
        collection.update_one(
            {"_id": result.inserted_id},
            {"$set": {"status": "PROCESSING"}}
        )

        # Perform the conversion
        success = convert_step(input_file, output_file, output_format)

        if not success:
            collection.update_one(
                {"_id": result.inserted_id},
                {"$set": {"status": "FAILED", "error": "Conversion failed"}}
            )
            return jsonify({"error": "Conversion failed", "conversion_id": conversion_id}), 500

        # Update status to UPLOADING
        collection.update_one(
            {"_id": result.inserted_id},
            {"$set": {"status": "UPLOADING"}}
        )

        # Upload to S3 if bucket is provided
        if s3_bucket:
            upload_success = upload_to_s3(output_file, s3_bucket)
            if not upload_success:
                collection.update_one(
                    {"_id": result.inserted_id},
                    {"$set": {"status": "FAILED", "error": "S3 upload failed"}}
                )
                return jsonify({"error": "S3 upload failed", "conversion_id": conversion_id}), 500

            # Generate pre-signed URL for the uploaded file
            s3_object_name = os.path.basename(output_file)  # Use the file name as the S3 object key
            s3_download_link = generate_presigned_url(s3_bucket, s3_object_name)

            if not s3_download_link:
                collection.update_one(
                    {"_id": result.inserted_id},
                    {"$set": {"status": "FAILED", "error": "Failed to generate S3 download link"}}
                )
                return jsonify({"error": "Failed to generate S3 download link", "conversion_id": conversion_id}), 500

        # Update status to COMPLETED
        collection.update_one(
            {"_id": result.inserted_id},
            {"$set": {"status": "COMPLETED", "s3_link": s3_download_link}}
        )

        return jsonify({
            "message": "File converted and uploaded successfully",
            "output_file": output_file,
            "conversion_id": conversion_id,
            "s3_download_link": s3_download_link  # Return the pre-signed URL
        }), 200

    except Exception as e:
        # Log error in MongoDB
        if 'result' in locals():
            collection.update_one(
                {"_id": result.inserted_id},
                {"$set": {"status": "FAILED", "error": str(e)}}
            )
        return jsonify({"error": str(e)}), 500
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
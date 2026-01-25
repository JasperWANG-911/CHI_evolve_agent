import os
import csv
from pathlib import Path

def scan_3d_files(folder_path, output_csv='3d_files_scan.csv'):
    """
    scans the "Asseets" folder for 3D files and generates a CSV record
    """
    
    # supported 3D file extensions 
    extensions = ['.fbx', '.obj', '.gltf', '.glb', '.dae', '.stl', '.blend']
    
    # store results
    results = []

    # convert to Path object
    root_path = Path(folder_path)

    # recursively scan the folder
    for file_path in root_path.rglob('*'):
        # check if it's a file and the extension matches
        if file_path.is_file() and file_path.suffix.lower() in extensions:
            # get the full path of the file
            full_path = str(file_path)

            # get the file name
            file_name = file_path.name
            
            # get the parent folder name as tag
            # if the file is directly under the root directory, use the root directory name
            if file_path.parent == root_path:
                tag = root_path.name
            else:
                tag = file_path.parent.name
            
            results.append([full_path, file_name, tag])

    # write to CSV file
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)

        # write header
        writer.writerow(['file path', 'file name', 'tag'])

        # write data
        writer.writerows(results)

    print(f"Scan complete! Found {len(results)} 3D files.")
    print(f"Results saved to: {output_csv}")

    return results

# Usage example
if __name__ == "__main__":
    # Specify the folder path to scan
    folder_to_scan = r"./Assets"  # Adjust this path as needed

    # Call the function to scan and generate CSV
    scan_3d_files(folder_to_scan, 'assets.csv')
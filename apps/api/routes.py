import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

from apps.api.schemas import VerificationResponse
from hbit.universal import UniversalEncoder, UniversalVerifier, UniversalVerificationStatus

router = APIRouter()
encoder = UniversalEncoder()
verifier = UniversalVerifier()

def remove_temp_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

@router.post("/encode", summary="Sign a file with H-Bit", response_class=FileResponse)
async def encode_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    passphrase: str = Form(...),
    device_id: str = Form("api-v1"),
    encrypt: bool = Form(False)
):
    """
    Apply an H-Bit signature to the uploaded file.
    Returns the signed file as a binary stream.
    """
    if not passphrase:
        raise HTTPException(status_code=400, detail="A passphrase is required to sign the file.")
        
    temp_input = ""
    temp_output = ""
    try:
        _, ext = os.path.splitext(file.filename) if file.filename else ("", "")
        fd_in, temp_input = tempfile.mkstemp(suffix=ext)
        with os.fdopen(fd_in, "wb") as f_in:
            f_in.write(await file.read())
            
        fd_out, temp_output = tempfile.mkstemp(suffix=f"_signed{ext}")
        os.close(fd_out)
        
        encoder.encode(
            file_path=temp_input,
            author_key=passphrase,
            output_path=temp_output,
            device_id=device_id,
            encrypt=encrypt
        )
        
        # We need to return the file, so we can't delete it immediately.
        # We'll use BackgroundTasks to delete the input and output temp files after the response is sent.
        background_tasks.add_task(remove_temp_file, temp_input)
        background_tasks.add_task(remove_temp_file, temp_output)
        
        return FileResponse(
            path=temp_output,
            media_type="application/octet-stream",
            filename=f"signed_{file.filename}" if file.filename else "signed_file"
        )
        
    except Exception as e:
        remove_temp_file(temp_input)
        remove_temp_file(temp_output)
        raise HTTPException(status_code=500, detail=f"Error signing file: {str(e)}")


@router.post("/verify", summary="Verify an H-Bit signed file", response_model=VerificationResponse)
async def verify_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    passphrase: Optional[str] = Form(None)
):
    """
    Verify the H-Bit signature of an uploaded file.
    Optionally provide a passphrase if the payload was encrypted.
    """
    temp_input = ""
    try:
        _, ext = os.path.splitext(file.filename) if file.filename else ("", "")
        fd_in, temp_input = tempfile.mkstemp(suffix=ext)
        with os.fdopen(fd_in, "wb") as f_in:
            f_in.write(await file.read())
            
        result = verifier.verify(
            file_path=temp_input,
            passphrase=passphrase
        )
        
        background_tasks.add_task(remove_temp_file, temp_input)
        
        # Prepare response
        response = VerificationResponse(
            status=result.status.name,
            message=result.message,
            confidence=0.0
        )
        
        if result.decode_result:
            dr = result.decode_result
            response.confidence = dr.confidence
            if dr.found:
                response.author_hash = dr.author_hash
                response.content_hash = dr.content_hash
                response.timestamp = dr.timestamp
                response.version = dr.version
                response.media_category = dr.media_category
                response.strategy_used = dr.strategy_used
                
        return response
        
    except Exception as e:
        remove_temp_file(temp_input)
        raise HTTPException(status_code=500, detail=f"Error verifying file: {str(e)}")
